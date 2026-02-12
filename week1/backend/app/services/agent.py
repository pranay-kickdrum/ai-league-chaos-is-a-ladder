"""Agentic controller – orchestrates the multi-round verification pipeline."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from app.config import settings
from app.models import EvidenceChunk, Verdict, VerifyResponse
from app.services.claim_extractor import extract_and_decompose
from app.services.citation_validator import validate_citations
from app.services.reasoner import (
    reformulate_query,
    verify_claim,
)
from app.services.embedder import embed_texts, store_verified_claim
from app.services.reranker import rerank
from app.services.retriever import batch_hybrid_retrieve, hybrid_retrieve
from app.services.web_search import web_search

logger = logging.getLogger(__name__)


def _elapsed(start: float) -> str:
    """Return formatted elapsed time since start."""
    return f"{(time.time() - start) * 1000:.0f}ms"


async def _followup_retrieval(
    sub_claim: str,
    accumulated_evidence: list[EvidenceChunk],
    seen_keys: set[str],
) -> tuple[list[EvidenceChunk], int, bool]:
    """Run web search + optional reformulation rounds for a sub-claim
    whose KB evidence was insufficient.

    Returns (final_evidence, extra_rounds_used, used_web).
    """
    max_extra = settings.max_retrieval_rounds - 1  # round 1 was the batch KB round
    query = sub_claim
    used_web = False

    for round_num in range(max_extra):
        logger.info(
            "      Follow-up round %d/%d: Query = '%s'",
            round_num + 1, max_extra, query[:100],
        )

        # Web search
        t0 = time.time()
        logger.info("        → Searching web via Tavily...")
        web_evidence = await web_search(query)
        logger.info("        Web: %d chunks [%s]", len(web_evidence), _elapsed(t0))
        used_web = True

        new_count = 0
        for e in web_evidence:
            key = e.text[:200]
            if key not in seen_keys:
                seen_keys.add(key)
                accumulated_evidence.append(e)
                new_count += 1

        if not accumulated_evidence:
            if round_num < max_extra - 1:
                t0 = time.time()
                query = await reformulate_query(query, [])
                logger.info("        ↻ Reformulated query [%s]", _elapsed(t0))
                continue
            return [], round_num + 1, used_web

        # Rerank ALL accumulated evidence (KB + Web)
        t0 = time.time()
        reranked = await rerank(query, accumulated_evidence)
        top_score = reranked[0].relevance_score if reranked else 0.0
        logger.info("        Reranked: top_score=%.3f, %d chunks [%s]",
                    top_score, len(reranked), _elapsed(t0))

        sufficient = top_score > 0.3 and len(reranked) >= 2
        if sufficient:
            logger.info("      ✓ Evidence sufficient after web search")
            return reranked, round_num + 1, used_web

        if round_num < max_extra - 1:
            t0 = time.time()
            query = await reformulate_query(query, reranked)
            logger.info("        ↻ Reformulated query [%s]", _elapsed(t0))
        else:
            return reranked, round_num + 1, used_web

    return accumulated_evidence, max_extra, used_web


async def run_verification_pipeline(
    raw_text: str,
    source_url: Optional[str] = None,
) -> VerifyResponse:
    """Full agentic verification pipeline: extract → decompose → retrieve → reason → cite.

    This is the main entry point called by the API endpoint.
    """
    pipeline_start = time.time()
    step_times: dict[str, float] = {}

    logger.info("")
    logger.info("╔" + "═" * 78 + "╗")
    logger.info("║  VERIFICATION PIPELINE STARTED" + " " * 47 + "║")
    logger.info("╚" + "═" * 78 + "╝")
    logger.info("")
    logger.info("  Input (%d chars): %s", len(raw_text),
                raw_text[:200] + ("..." if len(raw_text) > 200 else ""))
    logger.info("")

    # ──────────────────────────────────────────────────────────────────────
    #  STEP 1 — CLAIM EXTRACTION + DECOMPOSITION
    # ──────────────────────────────────────────────────────────────────────
    logger.info("┌─────────────────────────────────────────────────────────────────┐")
    logger.info("│  STEP 1/6 ▸ CLAIM EXTRACTION + DECOMPOSITION                  │")
    logger.info("└─────────────────────────────────────────────────────────────────┘")
    logger.info("")
    t0 = time.time()
    claim, sub_claims = await extract_and_decompose(raw_text)
    step_times["1_extract_decompose"] = time.time() - t0

    if claim == "NO_CLAIM" or not claim:
        logger.warning("  ✗ No verifiable claim found in input text")
        return VerifyResponse(
            claim=raw_text,
            verdict=Verdict.NOT_ENOUGH_EVIDENCE,
            confidence=0.0,
            reasoning="No verifiable factual claim could be extracted from the input text.",
            metadata={"extraction_result": "NO_CLAIM"},
        )

    logger.info("  ✓ Extracted claim : %s", claim)
    logger.info("  ✓ Sub-claims (%d) :", len(sub_claims))
    for i, sc in enumerate(sub_claims, 1):
        logger.info("      %d. %s", i, sc)
    logger.info("")
    logger.info("  ⏱  %s", _elapsed(t0))
    logger.info("")

    # ──────────────────────────────────────────────────────────────────────
    #  STEP 2 — EVIDENCE RETRIEVAL
    # ──────────────────────────────────────────────────────────────────────
    logger.info("┌─────────────────────────────────────────────────────────────────┐")
    logger.info("│  STEP 2/6 ▸ EVIDENCE RETRIEVAL (KB → Rerank → Web if needed)   │")
    logger.info("└─────────────────────────────────────────────────────────────────┘")
    logger.info("")
    t0 = time.time()
    all_evidence: list[EvidenceChunk] = []
    total_rounds = 0
    any_used_web = False

    # 2a. Batch-embed
    t_emb = time.time()
    sub_claim_embeddings = embed_texts(sub_claims)
    logger.info("  [2a] Batch-embedded %d sub-claim(s)  ⏱ %s", len(sub_claims), _elapsed(t_emb))

    # 2b. Batch KB retrieval
    t_kb = time.time()
    kb_results_per_sc = await batch_hybrid_retrieve(sub_claims, sub_claim_embeddings)
    logger.info("  [2b] Batch KB retrieval done          ⏱ %s", _elapsed(t_kb))

    # 2c. Rerank + sufficiency per sub-claim
    followup_tasks: list[tuple[int, asyncio.Task]] = []
    per_sc_evidence: list[list[EvidenceChunk]] = [[] for _ in sub_claims]
    per_sc_rounds: list[int] = [1] * len(sub_claims)
    per_sc_web: list[bool] = [False] * len(sub_claims)

    logger.info("")
    logger.info("  [2c] Per sub-claim rerank + sufficiency check:")
    for i, (sc, kb_evidence) in enumerate(zip(sub_claims, kb_results_per_sc)):
        logger.info("       ┌ Sub-claim %d: \"%s\"", i + 1, sc[:80])
        logger.info("       │  KB chunks returned: %d", len(kb_evidence))

        if not kb_evidence:
            logger.info("       │  → No KB evidence → scheduling web follow-up")
            logger.info("       └")
            seen: set[str] = set()
            task = asyncio.create_task(_followup_retrieval(sc, [], seen))
            followup_tasks.append((i, task))
            continue

        t_rr = time.time()
        reranked = await rerank(sc, kb_evidence)
        top_score = reranked[0].relevance_score if reranked else 0.0
        logger.info("       │  Rerank: %d chunks, top_score=%.3f  ⏱ %s",
                     len(reranked), top_score, _elapsed(t_rr))

        kb_sufficient = top_score > 0.5 and len(reranked) >= 2
        if kb_sufficient:
            logger.info("       │  ✓ KB sufficient — skipping web")
            per_sc_evidence[i] = reranked
        else:
            logger.info("       │  ✗ KB insufficient (score=%.3f) — scheduling web", top_score)
            seen = {e.text[:200] for e in reranked}
            task = asyncio.create_task(_followup_retrieval(sc, list(reranked), seen))
            followup_tasks.append((i, task))
        logger.info("       └")

    # 2d. Await web follow-ups
    if followup_tasks:
        logger.info("")
        logger.info("  [2d] Awaiting %d web follow-up(s) in parallel…", len(followup_tasks))
        task_results = await asyncio.gather(*(t for _, t in followup_tasks))
        for (idx, _), (evidence, extra_rounds, used_web) in zip(followup_tasks, task_results):
            per_sc_evidence[idx] = evidence
            per_sc_rounds[idx] += extra_rounds
            per_sc_web[idx] = used_web

    # 2e. Aggregate
    logger.info("")
    logger.info("  [2e] Aggregated evidence per sub-claim:")
    for i, (evidence, rounds, used_web) in enumerate(
        zip(per_sc_evidence, per_sc_rounds, per_sc_web)
    ):
        src = "KB+Web" if used_web else "KB"
        logger.info("       Sub-claim %d: %d chunks, %d round(s) [%s]",
                     i + 1, len(evidence), rounds, src)
        for j, e in enumerate(evidence, 1):
            logger.info("         %d. [rel=%.3f | cred=%.2f | %s] %s",
                         j, e.relevance_score, e.credibility_score,
                         e.retrieval_method[:3].upper(), e.source_name[:35])
            logger.info("            \"%s\"", e.text[:100].replace("\n", " "))
            if e.source_url:
                logger.info("            url: %s", e.source_url[:100])
        all_evidence.extend(evidence)
        total_rounds += rounds
        if used_web:
            any_used_web = True

    step_times["2_evidence_retrieval"] = time.time() - t0
    logger.info("")
    logger.info("  ⏱  %s", _elapsed(t0))
    logger.info("")

    # De-duplicate + filter system entries
    seen: set[str] = set()
    unique_evidence: list[EvidenceChunk] = []
    system_filtered = 0
    for e in all_evidence:
        if e.source_name == "Verified Claim (System)":
            system_filtered += 1
            continue
        key = e.text[:200]
        if key not in seen:
            seen.add(key)
            unique_evidence.append(e)

    # ──────────────────────────────────────────────────────────────────────
    #  STEP 3 — EVIDENCE CONSOLIDATION
    # ──────────────────────────────────────────────────────────────────────
    logger.info("┌─────────────────────────────────────────────────────────────────┐")
    logger.info("│  STEP 3/6 ▸ EVIDENCE CONSOLIDATION                             │")
    logger.info("└─────────────────────────────────────────────────────────────────┘")
    logger.info("")
    t0 = time.time()
    logger.info("  Raw chunks collected   : %d", len(all_evidence))
    logger.info("  System entries filtered : %d", system_filtered)
    logger.info("  Unique after dedup     : %d", len(unique_evidence))
    logger.info("  Retrieval rounds total : %d", total_rounds)

    # Fallback if low evidence
    if len(unique_evidence) < 3:
        logger.info("")
        logger.info("  ⚠  Low evidence (%d) — running fallback search with original claim", len(unique_evidence))
        fb_kb = await hybrid_retrieve(claim)
        new_from_fallback = 0
        for e in fb_kb:
            key = e.text[:200]
            if key not in seen:
                seen.add(key)
                unique_evidence.append(e)
                new_from_fallback += 1

        if len(unique_evidence) < 3:
            fb_web = await web_search(claim)
            any_used_web = True
            for e in fb_web:
                key = e.text[:200]
                if key not in seen:
                    seen.add(key)
                    unique_evidence.append(e)
                    new_from_fallback += 1

        logger.info("  Fallback added         : %d new chunks (total now: %d)",
                     new_from_fallback, len(unique_evidence))

        if new_from_fallback > 0 and len(unique_evidence) > settings.rerank_top_k:
            unique_evidence = await rerank(claim, unique_evidence)

    # Sort by relevance
    unique_evidence.sort(key=lambda e: e.relevance_score, reverse=True)

    kb_count = sum(1 for e in unique_evidence if e.retrieval_method == "knowledge_base")
    web_count = sum(1 for e in unique_evidence if e.retrieval_method == "web_search")
    logger.info("")
    logger.info("  Evidence breakdown     : %d KB  |  %d Web", kb_count, web_count)

    if unique_evidence:
        logger.info("")
        logger.info("  Top evidence chunks (sorted by relevance):")
        for j, e in enumerate(unique_evidence[:5], 1):
            logger.info("    %d. [rel=%.3f | cred=%.2f | %s] %s",
                         j, e.relevance_score, e.credibility_score,
                         e.retrieval_method[:3].upper(),
                         e.source_name[:40])
            logger.info("       text: \"%s\"", e.text[:120].replace("\n", " "))
            if e.source_url:
                logger.info("       url : %s", e.source_url[:100])

    step_times["3_consolidation"] = time.time() - t0
    logger.info("")
    logger.info("  ⏱  %s", _elapsed(t0))
    logger.info("")

    # ──────────────────────────────────────────────────────────────────────
    #  STEP 4 — LLM REASONING & VERIFICATION
    # ──────────────────────────────────────────────────────────────────────
    logger.info("┌─────────────────────────────────────────────────────────────────┐")
    logger.info("│  STEP 4/6 ▸ LLM REASONING & VERIFICATION                      │")
    logger.info("└─────────────────────────────────────────────────────────────────┘")
    logger.info("")
    t0 = time.time()
    logger.info("  Input → LLM:")
    logger.info("    Claim       : %s", claim[:120])
    logger.info("    Sub-claims  : %d", len(sub_claims))
    logger.info("    Evidence    : %d chunks (top-5 sent to LLM)", len(unique_evidence))
    logger.info("")

    result = await verify_claim(claim, sub_claims, unique_evidence)
    step_times["4_llm_reasoning"] = time.time() - t0

    logger.info("  Output ← LLM:")
    logger.info("    Verdict     : %s", result.verdict.value)
    logger.info("    Confidence  : %.2f", result.confidence)
    logger.info("    Reasoning   : %s", result.reasoning[:200])
    logger.info("    Sub-claims  : %d", len(result.sub_claims))
    for j, sc_res in enumerate(result.sub_claims, 1):
        logger.info("      %d. [%s] %s", j, sc_res.verdict.value, sc_res.text[:80])
        for s in sc_res.supporting_sources[:2]:
            logger.info("         + %s  url=%s", s.name[:40], (s.url or "—")[:60])
        for s in sc_res.contradicting_sources[:2]:
            logger.info("         − %s  url=%s", s.name[:40], (s.url or "—")[:60])
    logger.info("    Citations   : %d", len(result.citations))
    for j, c in enumerate(result.citations, 1):
        logger.info("      %d. %s  url=%s", j, c.source_name[:40], (c.url or "—")[:60])
        logger.info("         quote: \"%s\"", (c.relevant_quote or "")[:80])
    logger.info("")
    logger.info("  ⏱  %s", _elapsed(t0))
    logger.info("")

    # ──────────────────────────────────────────────────────────────────────
    #  STEP 4b — RETRY WITH WEB (if NOT_ENOUGH_EVIDENCE & no web yet)
    # ──────────────────────────────────────────────────────────────────────
    if result.verdict == Verdict.NOT_ENOUGH_EVIDENCE and not any_used_web:
        logger.info("┌─────────────────────────────────────────────────────────────────┐")
        logger.info("│  STEP 4b ▸ RETRY — web search (KB was insufficient)            │")
        logger.info("└─────────────────────────────────────────────────────────────────┘")
        logger.info("")
        t0 = time.time()
        web_evidence = await web_search(claim)
        web_only: list[EvidenceChunk] = []
        for e in web_evidence:
            key = e.text[:200]
            if key not in seen:
                seen.add(key)
                web_only.append(e)
                unique_evidence.append(e)
        any_used_web = True
        logger.info("  Web search returned %d new chunks", len(web_only))

        if web_only:
            logger.info("  Re-running LLM with %d web-only chunks…", len(web_only))
            result = await verify_claim(claim, sub_claims, web_only)
            logger.info("")
            logger.info("  Retry output:")
            logger.info("    Verdict     : %s", result.verdict.value)
            logger.info("    Confidence  : %.2f", result.confidence)
            logger.info("    Reasoning   : %s", result.reasoning[:200])

        step_times["4b_web_retry"] = time.time() - t0
        logger.info("")
        logger.info("  ⏱  %s", _elapsed(t0))
        logger.info("")

    # ──────────────────────────────────────────────────────────────────────
    #  STEP 5 — CITATION VALIDATION
    # ──────────────────────────────────────────────────────────────────────
    logger.info("┌─────────────────────────────────────────────────────────────────┐")
    logger.info("│  STEP 5/6 ▸ CITATION VALIDATION                                │")
    logger.info("└─────────────────────────────────────────────────────────────────┘")
    logger.info("")
    t0 = time.time()
    logger.info("  Input : %d LLM citations, %d evidence chunks to match against",
                 len(result.citations), len(unique_evidence))
    result = await validate_citations(result, unique_evidence)
    step_times["5_citation_validation"] = time.time() - t0

    logger.info("  Output: %d citations survived validation", len(result.citations))
    for j, c in enumerate(result.citations, 1):
        logger.info("    %d. %s (%.0f%% cred.)  url=%s",
                     j, c.source_name[:40], c.credibility_score * 100,
                     (c.url or "—")[:60])
    logger.info("")
    logger.info("  ⏱  %s", _elapsed(t0))
    logger.info("")

    # ──────────────────────────────────────────────────────────────────────
    #  STEP 6 — FEEDBACK LOOP
    # ──────────────────────────────────────────────────────────────────────
    total_elapsed = time.time() - pipeline_start
    result.metadata.update({
        "retrieval_rounds": total_rounds,
        "evidence_chunks_total": len(all_evidence),
        "evidence_chunks_unique": len(unique_evidence),
        "web_search_used": any_used_web,
        "timing": {k: f"{v*1000:.0f}ms" for k, v in step_times.items()},
        "total_time": f"{total_elapsed*1000:.0f}ms",
    })

    if result.verdict != Verdict.NOT_ENOUGH_EVIDENCE and result.confidence >= 0.3:
        logger.info("┌─────────────────────────────────────────────────────────────────┐")
        logger.info("│  STEP 6/6 ▸ FEEDBACK LOOP — Storing in KB                      │")
        logger.info("└─────────────────────────────────────────────────────────────────┘")
        logger.info("")
        t0 = time.time()
        try:
            evidence_dicts = [
                {
                    "text": e.text,
                    "source_name": e.source_name,
                    "source_url": e.source_url,
                    "publish_date": e.publish_date,
                    "credibility_score": e.credibility_score,
                    "retrieval_method": e.retrieval_method,
                }
                for e in unique_evidence
            ]
            citation_dicts = [
                {"source_name": c.source_name, "url": c.url, "quote": c.relevant_quote}
                for c in result.citations
            ]
            store_verified_claim(
                claim=claim,
                verdict=result.verdict.value,
                confidence=result.confidence,
                reasoning=result.reasoning,
                citations=citation_dicts,
                evidence_chunks=evidence_dicts,
            )
            result.metadata["feedback_stored"] = True
            logger.info("  ✓ Stored claim + %d citations + %d evidence chunks",
                         len(citation_dicts), len(evidence_dicts))
        except Exception as exc:
            logger.warning("  ⚠ Feedback loop failed (non-critical): %s", exc)
            result.metadata["feedback_stored"] = False
        step_times["6_feedback_loop"] = time.time() - t0
        logger.info("  ⏱  %s", _elapsed(t0))
        logger.info("")
    else:
        logger.info("")
        logger.info("  ℹ  Skipping feedback loop (verdict=%s, confidence=%.2f)",
                     result.verdict.value, result.confidence)
        result.metadata["feedback_stored"] = False
        logger.info("")

    # ──────────────────────────────────────────────────────────────────────
    #  SUMMARY
    # ──────────────────────────────────────────────────────────────────────
    total_elapsed = time.time() - pipeline_start

    logger.info("╔" + "═" * 78 + "╗")
    logger.info("║  PIPELINE COMPLETE" + " " * 59 + "║")
    logger.info("╠" + "═" * 78 + "╣")
    logger.info("║  Verdict     : %-62s║", result.verdict.value)
    logger.info("║  Confidence  : %-62s║", f"{result.confidence:.2f}")
    logger.info("║  Citations   : %-62s║", str(len(result.citations)))
    logger.info("║  KB Updated  : %-62s║", str(result.metadata.get("feedback_stored", False)))
    logger.info("╠" + "═" * 78 + "╣")
    logger.info("║  TIMING BREAKDOWN" + " " * 60 + "║")
    logger.info("║" + "─" * 78 + "║")
    for step_name, step_time in step_times.items():
        pct = (step_time / total_elapsed * 100) if total_elapsed > 0 else 0
        line = f"  {step_name:<25s} {step_time * 1000:>7.0f}ms  ({pct:>4.1f}%)"
        logger.info("║%-78s║", line)
    total_line = f"  {'TOTAL':<25s} {total_elapsed * 1000:>7.0f}ms  (100.0%)"
    logger.info("║" + "─" * 78 + "║")
    logger.info("║%-78s║", total_line)
    logger.info("╚" + "═" * 78 + "╝")
    logger.info("")

    return result
