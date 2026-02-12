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
from app.services.embedder import embed_texts, lookup_cached_verdict, store_verified_claim
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

    logger.info("=" * 80)
    logger.info("VERIFICATION PIPELINE STARTED")
    logger.info("=" * 80)
    logger.info("INPUT: %s", raw_text[:200] + ("..." if len(raw_text) > 200 else ""))
    
    # 1+2. Extract and decompose in ONE LLM call
    logger.info("\n[STEP 1/6] CLAIM EXTRACTION + DECOMPOSITION")
    logger.info("-" * 80)
    t0 = time.time()
    claim, sub_claims = await extract_and_decompose(raw_text)
    step_times["1_extract_decompose"] = time.time() - t0
    logger.info("EXTRACTED CLAIM: %s", claim)
    logger.info("⏱ Step 1 took: %s", _elapsed(t0))
    
    if claim == "NO_CLAIM" or not claim:
        logger.warning("No verifiable claim found in input text")
        return VerifyResponse(
            claim=raw_text,
            verdict=Verdict.NOT_ENOUGH_EVIDENCE,
            confidence=0.0,
            reasoning="No verifiable factual claim could be extracted from the input text.",
            metadata={"extraction_result": "NO_CLAIM"},
        )

    logger.info("DECOMPOSED INTO %d SUB-CLAIMS:", len(sub_claims))
    for i, sc in enumerate(sub_claims, 1):
        logger.info("  [%d] %s", i, sc)

    # 1b. Cache check – look for previously verified identical claim
    logger.info("\n[STEP 1b] CACHE CHECK – looking for cached verdict in ChromaDB")
    logger.info("-" * 80)
    t_cache = time.time()
    claim_emb = embed_texts([claim])[0]
    cached = lookup_cached_verdict(claim_emb)
    step_times["1b_cache_check"] = time.time() - t_cache
    logger.info("⏱ Cache check took: %s", _elapsed(t_cache))

    if cached:
        logger.info("=" * 80)
        logger.info("CACHE HIT – Returning stored verdict (similarity=%.3f)", cached["similarity"])
        logger.info("=" * 80)

        from app.models import Citation, SubClaimResult, SubClaimSource

        # Build citations from cached URLs
        cached_citations = [
            Citation(
                source_name=cu.get("source_name", "Cached Source"),
                url=cu.get("url", ""),
                relevant_quote="",
            )
            for cu in cached["citation_urls"]
            if cu.get("url")
        ]

        # Build minimal sub-claim results with the same cached citations as sources
        cached_sc_sources = [
            SubClaimSource(name=cu.get("source_name", ""), url=cu.get("url", ""))
            for cu in cached["citation_urls"]
            if cu.get("url")
        ]
        cached_sub_claims = [
            SubClaimResult(
                text=sc,
                verdict=Verdict(cached["verdict"]),
                evidence_summary="Retrieved from cached verification.",
                supporting_sources=list(cached_sc_sources),
            )
            for sc in sub_claims
        ]

        total_elapsed = time.time() - pipeline_start
        return VerifyResponse(
            claim=claim,
            verdict=Verdict(cached["verdict"]),
            confidence=cached["confidence"],
            reasoning=cached["reasoning"],
            sub_claims=cached_sub_claims,
            citations=cached_citations,
            metadata={
                "cache_hit": True,
                "cache_similarity": cached["similarity"],
                "timing": {k: f"{v*1000:.0f}ms" for k, v in step_times.items()},
                "total_time": f"{total_elapsed*1000:.0f}ms",
            },
        )
    else:
        logger.info("  Cache MISS – proceeding with full pipeline")

    # 2. Retrieve evidence for each sub-claim (batched)
    logger.info("\n[STEP 2/6] EVIDENCE RETRIEVAL (KB-FIRST, WEB IF NEEDED)")
    logger.info("-" * 80)
    t0 = time.time()
    all_evidence: list[EvidenceChunk] = []
    total_rounds = 0
    any_used_web = False

    # --- 2a. Batch-embed all sub-claims in ONE OpenAI call ---
    #     If a sub-claim equals the claim itself, reuse the embedding from cache check
    t_emb = time.time()
    if len(sub_claims) == 1 and sub_claims[0] == claim:
        logger.info("Single sub-claim equals claim – reusing cache-check embedding")
        sub_claim_embeddings = [claim_emb]
    else:
        logger.info("Batch-embedding %d sub-claim(s) in a single API call...", len(sub_claims))
        sub_claim_embeddings = embed_texts(sub_claims)
    logger.info("  ✓ Batch embedding done [%s]", _elapsed(t_emb))

    # --- 2b. Batch KB retrieval: ONE ChromaDB call + per-query BM25 + RRF ---
    t_kb = time.time()
    logger.info("Batch KB retrieval for %d sub-claim(s)...", len(sub_claims))
    kb_results_per_sc = await batch_hybrid_retrieve(
        sub_claims, sub_claim_embeddings,
    )
    logger.info("  ✓ Batch KB retrieval done [%s]", _elapsed(t_kb))

    # --- 2c. Per sub-claim: rerank KB evidence, check sufficiency ---
    #     If KB insufficient → fire web search follow-up (in parallel)
    followup_tasks: list[tuple[int, asyncio.Task]] = []
    per_sc_evidence: list[list[EvidenceChunk]] = [[] for _ in sub_claims]
    per_sc_rounds: list[int] = [1] * len(sub_claims)
    per_sc_web: list[bool] = [False] * len(sub_claims)

    for i, (sc, kb_evidence) in enumerate(zip(sub_claims, kb_results_per_sc)):
        logger.info("  Sub-claim %d: KB returned %d chunks", i + 1, len(kb_evidence))

        if not kb_evidence:
            logger.info("    → No KB evidence, scheduling web follow-up")
            seen: set[str] = set()
            task = asyncio.create_task(
                _followup_retrieval(sc, [], seen)
            )
            followup_tasks.append((i, task))
            continue

        # Rerank KB evidence
        t_rr = time.time()
        reranked = await rerank(sc, kb_evidence)
        top_score = reranked[0].relevance_score if reranked else 0.0
        logger.info("    Rerank: top_score=%.3f, %d chunks [%s]",
                    top_score, len(reranked), _elapsed(t_rr))

        kb_sufficient = top_score > 0.5 and len(reranked) >= 2
        if kb_sufficient:
            logger.info("    ✓ KB sufficient – skipping web")
            per_sc_evidence[i] = reranked
        else:
            logger.info("    ✗ KB insufficient – scheduling web follow-up")
            seen = {e.text[:200] for e in reranked}
            task = asyncio.create_task(
                _followup_retrieval(sc, list(reranked), seen)
            )
            followup_tasks.append((i, task))

    # --- 2d. Await all web follow-ups in parallel ---
    if followup_tasks:
        logger.info("  Awaiting %d web follow-up(s) in parallel...", len(followup_tasks))
        task_results = await asyncio.gather(*(t for _, t in followup_tasks))
        for (idx, _), (evidence, extra_rounds, used_web) in zip(followup_tasks, task_results):
            per_sc_evidence[idx] = evidence
            per_sc_rounds[idx] += extra_rounds
            per_sc_web[idx] = used_web

    # --- 2e. Aggregate ---
    for i, (evidence, rounds, used_web) in enumerate(
        zip(per_sc_evidence, per_sc_rounds, per_sc_web)
    ):
        source_type = "KB+Web" if used_web else "KB only"
        logger.info("Sub-claim %d: %d chunks, %d round(s) (%s)",
                    i + 1, len(evidence), rounds, source_type)
        all_evidence.extend(evidence)
        total_rounds += rounds
        if used_web:
            any_used_web = True

    step_times["2_evidence_retrieval"] = time.time() - t0
    logger.info("⏱ Step 2 took: %s", _elapsed(t0))

    # De-duplicate evidence (by first 200 chars of text)
    seen: set[str] = set()
    unique_evidence: list[EvidenceChunk] = []
    for e in all_evidence:
        key = e.text[:200]
        if key not in seen:
            seen.add(key)
            unique_evidence.append(e)

    logger.info("\n[STEP 3/6] EVIDENCE CONSOLIDATION + WEB CITATION ENRICHMENT")
    logger.info("-" * 80)
    t0 = time.time()
    logger.info("Total evidence chunks: %d (before dedup)", len(all_evidence))
    logger.info("Unique evidence chunks: %d (after dedup)", len(unique_evidence))
    logger.info("Total retrieval rounds: %d", total_rounds)

    # FALLBACK: If sub-claims yielded very little evidence, try the original broad claim
    if len(unique_evidence) < 3:
        logger.info("[STEP 3b] FALLBACK - Searching with original claim (low evidence: %d chunks)", len(unique_evidence))
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
        
        logger.info("  Fallback search found %d new evidence chunks (total now: %d)",
                    new_from_fallback, len(unique_evidence))
        
        if new_from_fallback > 0 and len(unique_evidence) > settings.rerank_top_k:
            unique_evidence = await rerank(claim, unique_evidence)
            logger.info("  Re-ranked expanded evidence to top-%d", len(unique_evidence))

    kb_count = sum(1 for e in unique_evidence if e.retrieval_method == "knowledge_base")
    web_count = sum(1 for e in unique_evidence if e.retrieval_method == "web_search")
    logger.info("Evidence sources: %d from KB, %d from Web", kb_count, web_count)
    step_times["3_consolidation"] = time.time() - t0
    logger.info("⏱ Step 3 took: %s", _elapsed(t0))

    # 4. LLM reasoning
    logger.info("\n[STEP 4/6] LLM REASONING & VERIFICATION")
    logger.info("-" * 80)
    t0 = time.time()
    logger.info("Passing %d evidence chunks to LLM for analysis", len(unique_evidence))
    result = await verify_claim(claim, sub_claims, unique_evidence)
    step_times["4_llm_reasoning"] = time.time() - t0
    logger.info("LLM VERDICT: %s (confidence: %.2f)", result.verdict.value, result.confidence)
    logger.info("⏱ Step 4 took: %s", _elapsed(t0))

    # 5. Citation validation
    logger.info("\n[STEP 5/6] CITATION VALIDATION")
    logger.info("-" * 80)
    t0 = time.time()
    logger.info("Validating %d citations from LLM", len(result.citations))
    result = await validate_citations(result, unique_evidence)
    step_times["5_citation_validation"] = time.time() - t0
    logger.info("Validated citations: %d survived validation", len(result.citations))
    logger.info("⏱ Step 5 took: %s", _elapsed(t0))

    # 6. Enrich metadata
    total_elapsed = time.time() - pipeline_start
    result.metadata.update({
        "retrieval_rounds": total_rounds,
        "evidence_chunks_total": len(all_evidence),
        "evidence_chunks_unique": len(unique_evidence),
        "web_search_used": any_used_web,
        "timing": {k: f"{v*1000:.0f}ms" for k, v in step_times.items()},
        "total_time": f"{total_elapsed*1000:.0f}ms",
    })

    # 7. FEEDBACK LOOP: Store verified claim + web evidence back into KB
    if result.verdict != Verdict.NOT_ENOUGH_EVIDENCE and result.confidence >= 0.3:
        logger.info("\n[STEP 6/6] FEEDBACK LOOP - Updating KB")
        logger.info("-" * 80)
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
            logger.info("  ✓ KB updated [%s]", _elapsed(t0))
        except Exception as exc:
            logger.warning("  ⚠ Feedback loop failed (non-critical): %s", exc)
            result.metadata["feedback_stored"] = False
        step_times["6_feedback_loop"] = time.time() - t0
    else:
        logger.info("\n  Skipping feedback loop (verdict=%s, confidence=%.2f)",
                    result.verdict.value, result.confidence)
        result.metadata["feedback_stored"] = False

    total_elapsed = time.time() - pipeline_start

    logger.info("\n" + "=" * 80)
    logger.info("VERIFICATION PIPELINE COMPLETED")
    logger.info("=" * 80)
    logger.info("FINAL VERDICT: %s", result.verdict.value)
    logger.info("CONFIDENCE: %.2f", result.confidence)
    logger.info("CITATIONS: %d", len(result.citations))
    logger.info("KB UPDATED: %s", result.metadata.get("feedback_stored", False))
    logger.info("─" * 40)
    logger.info("⏱ TIMING BREAKDOWN:")
    for step_name, step_time in step_times.items():
        pct = (step_time / total_elapsed * 100) if total_elapsed > 0 else 0
        logger.info("  %-25s %7.0fms  (%4.1f%%)", step_name, step_time * 1000, pct)
    logger.info("  %-25s %7.0fms  (100%%)", "TOTAL", total_elapsed * 1000)
    logger.info("=" * 80 + "\n")

    return result
