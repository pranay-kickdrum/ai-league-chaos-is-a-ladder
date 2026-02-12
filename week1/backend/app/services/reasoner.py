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
You are a rigorous but resourceful fact-checking assistant. Given a CLAIM and EVIDENCE, \
determine the verdict.

INSTRUCTIONS:
1. Analyze each piece of evidence for relevance to the claim.
2. Identify SUPPORTING evidence and CONTRADICTING evidence.
3. Consider the credibility and recency of each source.
4. If the claim contains multiple parts, evaluate each separately.
5. Determine a verdict: TRUE, FALSE, MISLEADING, or NOT_ENOUGH_EVIDENCE.

IMPORTANT - MAKING A DETERMINATION:
- TRY HARD to reach a TRUE, FALSE, or MISLEADING verdict. Use logical inference, \
  cross-referencing, and contextual reasoning to bridge gaps in the evidence.
- If evidence partially addresses the claim, use what's available and note limitations \
  in your reasoning. Partial evidence is still useful.
- Use MISLEADING when the claim is technically true but presented in a deceptive way, \
  or when the truth is more nuanced than the claim suggests.
- Only use NOT_ENOUGH_EVIDENCE as an absolute LAST RESORT when the evidence is \
  completely unrelated to the claim topic and you cannot make any reasonable inference.
- If you have evidence about the general topic but not the exact claim, still attempt \
  a verdict with lower confidence (0.3-0.5) rather than giving up.

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
- Explain your reasoning transparently, including what evidence supports/contradicts the claim.
- confidence must be a float between 0.0 and 1.0.
- Lower confidence is FINE – a verdict with 0.4 confidence is more useful than NOT_ENOUGH_EVIDENCE."""


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
determine whether the evidence contains ANY relevant information that could help verify \
or refute the claim.

Be GENEROUS in your assessment:
- If ANY evidence passage mentions the topic, entities, or events in the claim, that counts.
- Even partial or indirect evidence is useful (e.g., evidence about related events, \
  background context, or corroborating details).
- Only say INSUFFICIENT if the evidence is completely unrelated to the claim topic.

Reply with ONLY one word: "SUFFICIENT" or "INSUFFICIENT"."""


async def check_evidence_sufficiency(
    claim: str, evidence: list[EvidenceChunk]
) -> bool:
    """Quick LLM check: is the evidence sufficient to verify the claim?"""
    if not evidence:
        return False

    # Use more context: top-8 chunks, 500 chars each
    context = "\n".join(f"- {e.text[:500]}" for e in evidence[:8])
    client = _get_client()

    logger.debug("Checking evidence sufficiency for claim (using top-%d chunks)", min(8, len(evidence)))
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
You are a search-query reformulation expert. The original query did not return \
sufficient evidence. Your job is to create a BETTER search query.

Use these strategies:
1. SIMPLIFY: Remove unnecessary words, keep only key entities and facts.
2. BROADEN: If too specific, make it broader (e.g., "GDP growth India Q3 2024" → "India economic growth 2024").
3. SYNONYMS: Try alternative names, terms, or phrasings people might use.
4. ENTITY-FOCUSED: Focus on the main entity (person, company, country) + the key fact.
5. DIFFERENT ANGLE: If searching for a claim about X, try searching for the context around X.

Return ONLY the new search query (one line, no explanation). Make it concise and search-engine friendly."""


async def reformulate_query(
    original_query: str, evidence: list[EvidenceChunk]
) -> str:
    """Reformulate a query based on what evidence was found (or not found)."""
    context_summary = "; ".join(e.text[:150] for e in evidence[:3]) if evidence else "No evidence found at all."
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
        temperature=0.4,
        max_tokens=128,
    )
    new_query = resp.choices[0].message.content.strip()
    logger.debug("Reformulated query: '%s'", new_query[:80])
    return new_query
