"""LLM reasoning module for claim verification."""

from __future__ import annotations

import json
import logging
import time
from typing import Optional

from openai import AsyncOpenAI

from app.config import settings
from app.models import (
    Citation,
    EvidenceChunk,
    LLMVerificationOutput,
    SubClaimResult,
    SubClaimSource,
    Verdict,
    VerifyResponse,
)

logger = logging.getLogger(__name__)

_client: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


# ---------------------------------------------------------------------------
# Context assembly
# ---------------------------------------------------------------------------

MAX_EVIDENCE_FOR_LLM = 5      # send at most this many chunks
MAX_CHUNK_CHARS = 400          # truncate each chunk to this length


def assemble_context(evidence: list[EvidenceChunk]) -> str:
    """Format evidence chunks into the context block for the LLM prompt.

    Keeps only the top-N most relevant chunks and truncates each to stay
    within a reasonable token budget so the LLM responds faster.
    Includes relevance scores so the LLM can judge which evidence to trust.
    URLs are NOT shown to the LLM -- citations are built programmatically.
    """
    top = evidence[:MAX_EVIDENCE_FOR_LLM]
    parts: list[str] = []
    for i, e in enumerate(top, 1):
        text = e.text[:MAX_CHUNK_CHARS] + ("..." if len(e.text) > MAX_CHUNK_CHARS else "")
        parts.append(
            f"[Source {i}] (relevance: {e.relevance_score:.2f}, "
            f"credibility: {e.credibility_score:.2f}): {text}\n"
            f"  (from: {e.source_name}, date: {e.publish_date})"
        )
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Verification prompt
# ---------------------------------------------------------------------------

VERIFY_SYSTEM = """\
Fact-checker. Given CLAIM + EVIDENCE, return a JSON verdict. Be concise.

IMPORTANT: Some evidence may be IRRELEVANT to the claim (retrieved from a general database). \
IGNORE any evidence that is not directly about the specific claim topic. \
Each evidence has a "relevance" score — lower scores are less likely to be relevant.

VERDICTS: TRUE, FALSE, MISLEADING, NOT_ENOUGH_EVIDENCE (last resort only).
Use partial evidence with lower confidence rather than NOT_ENOUGH_EVIDENCE.

JSON FORMAT (raw JSON, no markdown fences):
{
  "sub_claims": [
    {"text": "sub-claim", "verdict": "TRUE|FALSE|MISLEADING|NOT_ENOUGH_EVIDENCE",
     "support": [1, 3],
     "contradict": [2]}
  ],
  "verdict": "TRUE|FALSE|MISLEADING|NOT_ENOUGH_EVIDENCE",
  "confidence": 0.85,
  "reasoning": "2-3 sentences max.",
  "relevant_sources": [1, 3, 5]
}

RULES:
- "support" and "contradict" are arrays of Source NUMBERS (e.g. 1, 2, 3) from the evidence.
- "relevant_sources" lists ALL Source numbers that are relevant to the claim (used for citation).
- Do NOT output URLs. Citations are built separately from evidence metadata.
- "reasoning" must be 2-3 sentences, not longer.
- confidence: float 0.0-1.0."""


def _source_ref_to_subclaim_source(
    idx: int, evidence: list[EvidenceChunk],
) -> SubClaimSource | None:
    """Convert a 1-based source index from the LLM into a SubClaimSource."""
    pos = idx - 1  # LLM uses 1-based indices
    if 0 <= pos < len(evidence):
        e = evidence[pos]
        return SubClaimSource(
            name=e.source_name,
            url=e.source_url,
            summary=e.text[:120],
        )
    return None


def _build_citations_from_evidence(
    relevant_indices: list[int],
    evidence: list[EvidenceChunk],
) -> list[Citation]:
    """Build Citation objects from evidence chunks the LLM flagged as relevant.

    ONLY evidence that the LLM explicitly listed in ``relevant_sources`` is
    cited — this prevents unrelated DB evidence (e.g. a Trump/Biden claim
    appearing as a citation for a Lata/Asha query) from leaking through.
    Deduplicates by URL.
    """
    seen_urls: set[str] = set()
    citations: list[Citation] = []
    top = evidence[:MAX_EVIDENCE_FOR_LLM]

    for idx in relevant_indices:
        pos = idx - 1
        if 0 <= pos < len(top):
            e = top[pos]
            url = e.source_url
            if url and url not in seen_urls:
                seen_urls.add(url)
                citations.append(Citation(
                    source_name=e.source_name,
                    url=url,
                    relevant_quote=e.text[:200].strip(),
                    credibility_score=e.credibility_score,
                    retrieval_method=e.retrieval_method,
                ))

    return citations


async def verify_claim(
    claim: str,
    sub_claims: list[str],
    evidence: list[EvidenceChunk],
) -> VerifyResponse:
    """Run the LLM verification reasoning and return a structured VerifyResponse.

    The LLM only outputs verdict / confidence / reasoning / sub-claims
    (referencing evidence by source number). Citations are built
    programmatically from the evidence chunks — no URLs ever pass through
    the LLM.
    """
    used_count = min(len(evidence), MAX_EVIDENCE_FOR_LLM)
    logger.info("  Assembling context: %d/%d evidence chunks, %d chars/chunk max",
                used_count, len(evidence), MAX_CHUNK_CHARS)
    context = assemble_context(evidence)
    logger.info("  Context → %d chars (~%d tokens)", len(context), len(context) // 4)

    client = _get_client()

    user_msg = f"CLAIM: {claim}\n\nEVIDENCE:\n{context}"

    logger.info("  Calling %s …", settings.fast_llm_model)
    t_llm = time.time()
    resp = await client.chat.completions.create(
        model=settings.fast_llm_model,
        messages=[
            {"role": "system", "content": VERIFY_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.0,
        max_tokens=1024,
    )
    llm_ms = (time.time() - t_llm) * 1000

    raw = resp.choices[0].message.content.strip()
    logger.info("  LLM responded in %.0fms (%d chars)", llm_ms, len(raw))

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
    if raw.endswith("```"):
        raw = raw.rsplit("```", 1)[0]
    raw = raw.strip()

    # Log raw JSON response for debugging
    logger.info("  Raw LLM JSON:")
    for line in raw.split("\n"):
        logger.info("    │ %s", line)

    try:
        parsed = json.loads(raw)
        llm_out = LLMVerificationOutput(**parsed)
        logger.info("  ✓ Parsed successfully")
    except (json.JSONDecodeError, Exception) as exc:
        logger.error("  ✗ Failed to parse LLM output: %s", exc)
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

    # Build sub-claim results — support/contradict are now source numbers
    top_evidence = evidence[:MAX_EVIDENCE_FOR_LLM]
    sub_results: list[SubClaimResult] = []
    for sc in llm_out.sub_claims:
        raw_support = sc.get("support", [])
        raw_contradict = sc.get("contradict", [])

        supporting: list[SubClaimSource] = []
        for ref in raw_support:
            if isinstance(ref, int):
                src = _source_ref_to_subclaim_source(ref, top_evidence)
                if src:
                    supporting.append(src)

        contradicting: list[SubClaimSource] = []
        for ref in raw_contradict:
            if isinstance(ref, int):
                src = _source_ref_to_subclaim_source(ref, top_evidence)
                if src:
                    contradicting.append(src)

        summary_parts = [s.summary or s.name for s in supporting]
        evidence_summary = "; ".join(summary_parts)

        sub_results.append(
            SubClaimResult(
                text=sc.get("text", ""),
                verdict=verdict_map.get(
                    sc.get("verdict", "").upper(), Verdict.NOT_ENOUGH_EVIDENCE
                ),
                evidence_summary=evidence_summary,
                supporting_sources=supporting,
                contradicting_sources=contradicting,
            )
        )

    # Build citations directly from evidence chunks (NOT from LLM output)
    citations = _build_citations_from_evidence(
        llm_out.relevant_sources, top_evidence,
    )
    logger.info("  Built %d citations from evidence (LLM flagged %d relevant sources)",
                len(citations), len(llm_out.relevant_sources))

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
    resp = await client.chat.completions.create(
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
    resp = await client.chat.completions.create(
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
