"""Agentic controller – orchestrates the multi-round verification pipeline."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from app.config import settings
from app.models import EvidenceChunk, Verdict, VerifyResponse
from app.services.claim_extractor import decompose_claim, extract_claim
from app.services.citation_validator import validate_citations
from app.services.reasoner import (
    check_evidence_sufficiency,
    reformulate_query,
    verify_claim,
)
from app.services.reranker import rerank
from app.services.retriever import hybrid_retrieve
from app.services.web_search import web_search

logger = logging.getLogger(__name__)


async def _retrieve_evidence_for_subclaim(
    sub_claim: str,
) -> tuple[list[EvidenceChunk], int]:
    """Run the agentic retrieval loop for a single sub-claim.

    Returns (evidence_chunks, rounds_used).
    Accumulates evidence across rounds instead of discarding previous rounds.
    """
    max_rounds = settings.max_retrieval_rounds
    query = sub_claim
    accumulated_evidence: list[EvidenceChunk] = []
    seen_keys: set[str] = set()

    logger.info("  → Retrieving evidence for: '%s'", sub_claim[:100])

    for round_num in range(max_rounds):
        logger.info(
            "    Round %d/%d: Query = '%s'",
            round_num + 1,
            max_rounds,
            query[:100],
        )

        # Parallel retrieval: KB + Web
        kb_task = hybrid_retrieve(query)
        web_task = web_search(query)
        kb_evidence, web_evidence = await asyncio.gather(kb_task, web_task)

        logger.info("      KB: %d chunks, Web: %d chunks", len(kb_evidence), len(web_evidence))
        
        combined = kb_evidence + web_evidence

        # Accumulate new unique evidence across rounds
        new_count = 0
        for e in combined:
            key = e.text[:200]
            if key not in seen_keys:
                seen_keys.add(key)
                accumulated_evidence.append(e)
                new_count += 1

        logger.info("      New unique evidence this round: %d (total accumulated: %d)",
                    new_count, len(accumulated_evidence))

        if not accumulated_evidence:
            logger.warning("      ⚠ Still no evidence after round %d", round_num + 1)
            if round_num < max_rounds - 1:
                query = await reformulate_query(query, [])
                logger.info("      ↻ Reformulated query for next round")
                continue
            return [], round_num + 1

        # Rerank ALL accumulated evidence
        reranked = await rerank(query, accumulated_evidence)
        logger.info("      Reranked to top-%d chunks (from %d accumulated)",
                    len(reranked), len(accumulated_evidence))

        # Check sufficiency
        sufficient = await check_evidence_sufficiency(sub_claim, reranked)
        logger.info("      Evidence sufficiency: %s", "✓ SUFFICIENT" if sufficient else "✗ INSUFFICIENT")
        
        if sufficient:
            logger.info("    ✓ Evidence sufficient after %d round(s)", round_num + 1)
            return reranked, round_num + 1

        # Not sufficient – reformulate for next round
        if round_num < max_rounds - 1:
            query = await reformulate_query(query, reranked)
            logger.info("      ↻ Query reformulated for next attempt")
        else:
            # Last round – return whatever we have (don't throw it away!)
            logger.info("    ⚠ Max rounds reached, returning %d accumulated evidence chunks", len(reranked))
            return reranked, round_num + 1

    return accumulated_evidence if accumulated_evidence else [], max_rounds


async def run_verification_pipeline(
    raw_text: str,
    source_url: Optional[str] = None,
) -> VerifyResponse:
    """Full agentic verification pipeline: extract → decompose → retrieve → reason → cite.

    This is the main entry point called by the API endpoint.
    """
    logger.info("=" * 80)
    logger.info("VERIFICATION PIPELINE STARTED")
    logger.info("=" * 80)
    logger.info("INPUT: %s", raw_text[:200] + ("..." if len(raw_text) > 200 else ""))
    
    # 1. Extract the core claim
    logger.info("\n[STEP 1/7] CLAIM EXTRACTION")
    logger.info("-" * 80)
    claim = await extract_claim(raw_text)
    logger.info("EXTRACTED CLAIM: %s", claim)
    
    if claim == "NO_CLAIM" or not claim:
        logger.warning("No verifiable claim found in input text")
        return VerifyResponse(
            claim=raw_text,
            verdict=Verdict.NOT_ENOUGH_EVIDENCE,
            confidence=0.0,
            reasoning="No verifiable factual claim could be extracted from the input text.",
            metadata={"extraction_result": "NO_CLAIM"},
        )

    # 2. Decompose into sub-claims
    logger.info("\n[STEP 2/7] CLAIM DECOMPOSITION")
    logger.info("-" * 80)
    sub_claims = await decompose_claim(claim)
    logger.info("DECOMPOSED INTO %d SUB-CLAIMS:", len(sub_claims))
    for i, sc in enumerate(sub_claims, 1):
        logger.info("  [%d] %s", i, sc)

    # 3. Retrieve evidence for each sub-claim (can parallelise)
    logger.info("\n[STEP 3/7] EVIDENCE RETRIEVAL (AGENTIC LOOP)")
    logger.info("-" * 80)
    all_evidence: list[EvidenceChunk] = []
    total_rounds = 0

    tasks = [_retrieve_evidence_for_subclaim(sc) for sc in sub_claims]
    results = await asyncio.gather(*tasks)

    for i, (evidence, rounds) in enumerate(results, 1):
        logger.info("Sub-claim %d: Retrieved %d evidence chunks in %d rounds", i, len(evidence), rounds)
        all_evidence.extend(evidence)
        total_rounds += rounds

    # De-duplicate evidence (by first 200 chars of text)
    seen: set[str] = set()
    unique_evidence: list[EvidenceChunk] = []
    for e in all_evidence:
        key = e.text[:200]
        if key not in seen:
            seen.add(key)
            unique_evidence.append(e)

    logger.info("\n[STEP 4/7] EVIDENCE CONSOLIDATION")
    logger.info("-" * 80)
    logger.info("Total evidence chunks: %d (before dedup)", len(all_evidence))
    logger.info("Unique evidence chunks: %d (after dedup)", len(unique_evidence))
    logger.info("Total retrieval rounds: %d", total_rounds)

    # FALLBACK: If sub-claims yielded very little evidence, try the original broad claim
    if len(unique_evidence) < 3:
        logger.info("\n[STEP 4b/7] FALLBACK - Searching with original claim (low evidence: %d chunks)", len(unique_evidence))
        logger.info("-" * 80)
        fb_kb = await hybrid_retrieve(claim)
        fb_web = await web_search(claim)
        fb_combined = fb_kb + fb_web
        
        new_from_fallback = 0
        for e in fb_combined:
            key = e.text[:200]
            if key not in seen:
                seen.add(key)
                unique_evidence.append(e)
                new_from_fallback += 1
        
        logger.info("  Fallback search found %d new evidence chunks (total now: %d)",
                    new_from_fallback, len(unique_evidence))
        
        # Rerank the expanded evidence set
        if new_from_fallback > 0 and len(unique_evidence) > settings.rerank_top_k:
            unique_evidence = await rerank(claim, unique_evidence)
            logger.info("  Re-ranked expanded evidence to top-%d", len(unique_evidence))
    
    # Log evidence sources breakdown
    kb_count = sum(1 for e in unique_evidence if e.retrieval_method == "knowledge_base")
    web_count = sum(1 for e in unique_evidence if e.retrieval_method == "web_search")
    logger.info("Evidence sources: %d from KB, %d from Web", kb_count, web_count)

    # 5. LLM reasoning
    logger.info("\n[STEP 5/7] LLM REASONING & VERIFICATION")
    logger.info("-" * 80)
    logger.info("Passing %d evidence chunks to LLM for analysis", len(unique_evidence))
    result = await verify_claim(claim, sub_claims, unique_evidence)
    logger.info("LLM VERDICT: %s (confidence: %.2f)", result.verdict.value, result.confidence)

    # 6. Citation validation
    logger.info("\n[STEP 6/7] CITATION VALIDATION")
    logger.info("-" * 80)
    logger.info("Validating %d citations from LLM", len(result.citations))
    result = await validate_citations(result, unique_evidence)
    logger.info("Validated citations: %d survived validation", len(result.citations))

    # 6. Enrich metadata
    result.metadata.update({
        "retrieval_rounds": total_rounds,
        "evidence_chunks_total": len(all_evidence),
        "evidence_chunks_unique": len(unique_evidence),
    })

    logger.info("\n" + "=" * 80)
    logger.info("VERIFICATION PIPELINE COMPLETED")
    logger.info("=" * 80)
    logger.info("FINAL VERDICT: %s", result.verdict.value)
    logger.info("CONFIDENCE: %.2f", result.confidence)
    logger.info("CITATIONS: %d", len(result.citations))
    logger.info("=" * 80 + "\n")

    return result
