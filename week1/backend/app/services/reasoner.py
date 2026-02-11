"""LLM reasoning module for claim verification."""

from __future__ import annotations

import json
import logging
from typing import Optional

from openai import OpenAI

from app.config import settings
from app.models import (
    Citation,
    EvidenceChunk,
    LLMVerificationOutput,
    SubClaimResult,
    Verdict,
    VerifyResponse,
)

logger = logging.getLogger(__name__)

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


# ---------------------------------------------------------------------------
# Context assembly
# ---------------------------------------------------------------------------

def assemble_context(evidence: list[EvidenceChunk]) -> str:
    """Format evidence chunks into the context block for the LLM prompt."""
    parts: list[str] = []
    for i, e in enumerate(evidence, 1):
        parts.append(
            f"[Source {i}]: {e.text}\n"
            f"  (from: {e.source_name}, date: {e.publish_date}, "
            f"url: {e.source_url}, credibility: {e.credibility_score:.2f})"
        )
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Verification prompt
# ---------------------------------------------------------------------------

VERIFY_SYSTEM = """\
You are a rigorous fact-checking assistant. Given a CLAIM and EVIDENCE, determine the verdict.

INSTRUCTIONS:
1. Analyze each piece of evidence for relevance to the claim.
2. Identify SUPPORTING evidence and CONTRADICTING evidence.
3. Consider the credibility and recency of each source.
4. If the claim contains multiple parts, evaluate each separately.
5. Determine a verdict: TRUE, FALSE, MISLEADING, or NOT_ENOUGH_EVIDENCE.

RESPOND IN THIS EXACT JSON FORMAT (no markdown fences, just raw JSON):
{
  "sub_claims": [
    {"text": "...", "verdict": "TRUE|FALSE|MISLEADING|NOT_ENOUGH_EVIDENCE", "support": ["Source 1 summary"], "contradict": ["Source 3 summary"]}
  ],
  "verdict": "TRUE|FALSE|MISLEADING|NOT_ENOUGH_EVIDENCE",
  "confidence": 0.85,
  "reasoning": "Step-by-step explanation of how you reached the verdict...",
  "citations": [
    {"source_name": "Reuters", "url": "https://...", "relevant_quote": "exact quote from evidence"}
  ]
}

CRITICAL RULES:
- ONLY cite sources from the provided evidence. NEVER fabricate a source or URL.
- The "relevant_quote" MUST be an exact substring from the evidence text.
- If evidence is insufficient to determine truth, return verdict "NOT_ENOUGH_EVIDENCE".
- Explain your reasoning transparently.
- confidence must be a float between 0.0 and 1.0."""


async def verify_claim(
    claim: str,
    sub_claims: list[str],
    evidence: list[EvidenceChunk],
) -> VerifyResponse:
    """Run the LLM verification reasoning and return a structured VerifyResponse."""
    logger.info("Assembling context from %d evidence chunks", len(evidence))
    context = assemble_context(evidence)
    logger.debug("Context length: %d characters", len(context))
    
    client = _get_client()

    user_msg = f"CLAIM: {claim}\n\nEVIDENCE:\n{context}"
    
    logger.info("Calling LLM (%s) for verification", settings.llm_model)
    resp = client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": VERIFY_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.0,
        max_tokens=2048,
    )

    raw = resp.choices[0].message.content.strip()
    logger.debug("LLM response length: %d characters", len(raw))

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
    if raw.endswith("```"):
        raw = raw.rsplit("```", 1)[0]
    raw = raw.strip()

    try:
        parsed = json.loads(raw)
        llm_out = LLMVerificationOutput(**parsed)
        logger.info("✓ LLM response parsed successfully")
    except (json.JSONDecodeError, Exception) as exc:
        logger.error("Failed to parse LLM output: %s", exc)
        logger.debug("Raw LLM output: %s", raw[:500])
        return VerifyResponse(
            claim=claim,
            verdict=Verdict.NOT_ENOUGH_EVIDENCE,
            confidence=0.0,
            reasoning=f"LLM output could not be parsed. Raw: {raw[:300]}",
            metadata={"parse_error": True},
        )

    # Map verdict string → enum
    verdict_map = {
        "TRUE": Verdict.TRUE,
        "FALSE": Verdict.FALSE,
        "MISLEADING": Verdict.MISLEADING,
        "NOT_ENOUGH_EVIDENCE": Verdict.NOT_ENOUGH_EVIDENCE,
    }
    verdict = verdict_map.get(llm_out.verdict.upper(), Verdict.NOT_ENOUGH_EVIDENCE)

    logger.info("LLM verdict: %s (raw: '%s')", verdict.value, llm_out.verdict)
    logger.info("LLM confidence: %.2f", llm_out.confidence)
    logger.info("LLM produced %d sub-claims and %d citations", len(llm_out.sub_claims), len(llm_out.citations))

    # Build sub-claim results
    sub_results: list[SubClaimResult] = []
    for sc in llm_out.sub_claims:
        sub_results.append(
            SubClaimResult(
                text=sc.get("text", ""),
                verdict=verdict_map.get(
                    sc.get("verdict", "").upper(), Verdict.NOT_ENOUGH_EVIDENCE
                ),
                evidence_summary="; ".join(sc.get("support", [])),
                supporting_sources=sc.get("support", []),
                contradicting_sources=sc.get("contradict", []),
            )
        )

    # Build citations
    citations: list[Citation] = []
    for c in llm_out.citations:
        citations.append(
            Citation(
                source_name=c.get("source_name", "Unknown"),
                url=c.get("url", ""),
                relevant_quote=c.get("relevant_quote", ""),
                credibility_score=0.0,
                retrieval_method="unknown",
            )
        )

    return VerifyResponse(
        claim=claim,
        verdict=verdict,
        confidence=max(0.0, min(1.0, llm_out.confidence)),
        reasoning=llm_out.reasoning,
        sub_claims=sub_results,
        citations=citations,
        metadata={
            "sources_checked": len(evidence),
            "sub_claims_count": len(sub_results),
        },
    )


# ---------------------------------------------------------------------------
# Evidence sufficiency check (lightweight)
# ---------------------------------------------------------------------------

SUFFICIENCY_SYSTEM = """\
You are an evidence-sufficiency evaluator. Given a claim and retrieved evidence passages, \
determine whether the evidence is SUFFICIENT to verify or refute the claim.

Reply with ONLY one word: "SUFFICIENT" or "INSUFFICIENT"."""


async def check_evidence_sufficiency(
    claim: str, evidence: list[EvidenceChunk]
) -> bool:
    """Quick LLM check: is the evidence sufficient to verify the claim?"""
    if not evidence:
        return False

    context = "\n".join(f"- {e.text[:300]}" for e in evidence[:5])
    client = _get_client()

    logger.debug("Checking evidence sufficiency for claim")
    resp = client.chat.completions.create(
        model=settings.fast_llm_model,
        messages=[
            {"role": "system", "content": SUFFICIENCY_SYSTEM},
            {"role": "user", "content": f"CLAIM: {claim}\n\nEVIDENCE:\n{context}"},
        ],
        temperature=0.0,
        max_tokens=16,
    )
    answer = resp.choices[0].message.content.strip().upper()
    sufficient = "SUFFICIENT" in answer and "INSUFFICIENT" not in answer
    logger.debug("Sufficiency check result: %s (LLM: '%s')", "SUFFICIENT" if sufficient else "INSUFFICIENT", answer)
    return sufficient


# ---------------------------------------------------------------------------
# Query reformulation
# ---------------------------------------------------------------------------

REFORMULATE_SYSTEM = """\
You are a search-query reformulation assistant. The original query did not return \
sufficient evidence. Reformulate the query to find better evidence. \
Return ONLY the new search query (one line, no explanation)."""


async def reformulate_query(
    original_query: str, evidence: list[EvidenceChunk]
) -> str:
    """Reformulate a query based on what evidence was found (or not found)."""
    context_summary = "; ".join(e.text[:100] for e in evidence[:3])
    client = _get_client()

    logger.debug("Reformulating query (original: '%s')", original_query[:80])
    resp = client.chat.completions.create(
        model=settings.fast_llm_model,
        messages=[
            {"role": "system", "content": REFORMULATE_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Original query: {original_query}\n"
                    f"Evidence found so far: {context_summary}\n"
                    "Reformulated query:"
                ),
            },
        ],
        temperature=0.3,
        max_tokens=128,
    )
    new_query = resp.choices[0].message.content.strip()
    logger.debug("Reformulated query: '%s'", new_query[:80])
    return new_query
