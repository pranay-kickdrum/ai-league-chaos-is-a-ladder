"""Post-hoc citation validation – ensures every citation is grounded in evidence."""

from __future__ import annotations

import logging

from thefuzz import fuzz

from app.models import Citation, EvidenceChunk, Verdict, VerifyResponse

logger = logging.getLogger(__name__)

FUZZY_THRESHOLD = 60  # minimum partial-ratio match score (0-100)


def _best_match_score(quote: str, evidence: list[EvidenceChunk]) -> tuple[float, EvidenceChunk | None]:
    """Find the evidence chunk that best matches *quote*."""
    best_score = 0.0
    best_chunk = None
    for chunk in evidence:
        score = fuzz.partial_ratio(quote.lower(), chunk.text.lower())
        if score > best_score:
            best_score = score
            best_chunk = chunk
    return best_score, best_chunk


async def validate_citations(
    result: VerifyResponse,
    evidence: list[EvidenceChunk],
) -> VerifyResponse:
    """Validate and fix citations in the verification result.

    - Match each citation quote against the actual retrieved evidence.
    - Replace the URL with the real evidence source URL.
    - Strip citations that cannot be matched.
    - If zero citations survive, force NOT_ENOUGH_EVIDENCE.
    """
    if not result.citations:
        logger.info("No citations to validate")
        return result

    logger.info("Validating %d citation(s) from LLM", len(result.citations))
    
    validated: list[Citation] = []
    stripped_count = 0
    
    for i, cit in enumerate(result.citations, 1):
        if not cit.relevant_quote:
            logger.debug("  Citation %d: Empty quote, skipping", i)
            stripped_count += 1
            continue

        score, matched_chunk = _best_match_score(cit.relevant_quote, evidence)

        if score >= FUZZY_THRESHOLD and matched_chunk is not None:
            # Ground the citation in the real evidence
            cit.url = matched_chunk.source_url or cit.url
            cit.source_name = matched_chunk.source_name or cit.source_name
            cit.credibility_score = matched_chunk.credibility_score
            cit.retrieval_method = matched_chunk.retrieval_method
            validated.append(cit)
            logger.debug(
                "  Citation %d: ✓ VALIDATED (score=%d, source=%s)",
                i, score, cit.source_name
            )
        else:
            logger.warning(
                "  Citation %d: ✗ STRIPPED (score=%d < %d, quote='%s')",
                i, score, FUZZY_THRESHOLD, cit.relevant_quote[:60]
            )
            stripped_count += 1

    result.citations = validated

    if not validated and result.verdict != Verdict.NOT_ENOUGH_EVIDENCE:
        logger.warning("All citations stripped → forcing verdict to NOT_ENOUGH_EVIDENCE")
        result.verdict = Verdict.NOT_ENOUGH_EVIDENCE
        result.reasoning += " [All citations could not be verified against retrieved evidence.]"

    logger.info(
        "Citation validation complete: %d validated, %d stripped",
        len(validated),
        stripped_count,
    )
    return result
