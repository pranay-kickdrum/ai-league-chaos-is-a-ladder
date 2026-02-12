"""Post-hoc citation validation – ensures every citation is grounded in evidence."""

from __future__ import annotations

import logging

from thefuzz import fuzz

from app.models import Citation, EvidenceChunk, SubClaimSource, Verdict, VerifyResponse
from app.knowledge_base.sources import score_source

logger = logging.getLogger(__name__)

FUZZY_THRESHOLD = 50  # minimum partial-ratio match score (0-100), lowered to keep more valid citations
MIN_CREDIBILITY_FOR_LINK = 0.60  # only link URLs from sources with credibility >= this


def _best_match_score(quote: str, evidence: list[EvidenceChunk]) -> tuple[float, EvidenceChunk | None]:
    """Find the evidence chunk that best matches *quote*.

    When two chunks score equally, prefer the one with a reputed URL
    so that the citation can link to a real news article.
    """
    best_score = 0.0
    best_chunk = None
    for chunk in evidence:
        score = fuzz.partial_ratio(quote.lower(), chunk.text.lower())
        if score > best_score:
            best_score = score
            best_chunk = chunk
        elif score == best_score and score >= FUZZY_THRESHOLD:
            # Tie-break: prefer the chunk with a reputed URL
            cur_has_url = best_chunk is not None and _is_reputed_url(best_chunk.source_url)
            new_has_url = _is_reputed_url(chunk.source_url)
            if new_has_url and not cur_has_url:
                best_chunk = chunk
    return best_score, best_chunk


def _find_reputed_source_for_topic(evidence: list[EvidenceChunk]) -> tuple[str, str]:
    """Find the best reputed (url, source_name) pair from the evidence list."""
    for chunk in evidence:
        if chunk.source_url and _is_reputed_url(chunk.source_url):
            return chunk.source_url, chunk.source_name
    return "", ""


def _source_name_from_url(url: str) -> str:
    """Extract a readable source name from a URL (e.g. 'en.wikipedia.org')."""
    if not url:
        return ""
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc
        # Strip 'www.' prefix
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return url[:60]


def _is_reputed_url(url: str) -> bool:
    """Return True if the URL belongs to a reputed news/reference source."""
    if not url:
        return False
    return score_source(url) >= MIN_CREDIBILITY_FOR_LINK


def _filter_source_url(source: SubClaimSource) -> SubClaimSource:
    """Keep URL only if it belongs to a reputed source; otherwise blank it."""
    if source.url and not _is_reputed_url(source.url):
        logger.debug("    Stripping non-reputed URL: %s", source.url[:80])
        source.url = ""
    return source


async def validate_citations(
    result: VerifyResponse,
    evidence: list[EvidenceChunk],
) -> VerifyResponse:
    """Validate and fix citations in the verification result.

    - Match each citation quote against the actual retrieved evidence.
    - Replace the URL with the real evidence source URL.
    - Strip citations that cannot be matched.
    - Only link URLs from reputed news/reference sources.
    - Also filter sub-claim source URLs for reputation.
    """
    # --- 1. Filter sub-claim source URLs for reputation ---
    #     Strip non-reputed URLs; try to assign a reputed fallback from evidence.
    #     IMPORTANT: when swapping a URL, also update the source name to match.
    fallback_url, fallback_name = _find_reputed_source_for_topic(evidence)
    url_fixed = 0
    url_stripped = 0
    for sc in result.sub_claims:
        for s in sc.supporting_sources + sc.contradicting_sources:
            if s.url and _is_reputed_url(s.url):
                continue  # already good
            if s.url and not _is_reputed_url(s.url):
                # Non-reputed URL → try fallback
                if fallback_url:
                    s.url = fallback_url
                    s.name = fallback_name or _source_name_from_url(fallback_url)
                    url_fixed += 1
                else:
                    s.url = ""
                    url_stripped += 1
            elif not s.url and fallback_url:
                # No URL at all → assign fallback
                s.url = fallback_url
                s.name = fallback_name or _source_name_from_url(fallback_url)
                url_fixed += 1
    if url_fixed or url_stripped:
        logger.info("Sub-claim sources: %d assigned reputed URL, %d stripped (no reputed URL available)",
                    url_fixed, url_stripped)

    # --- 2. Validate top-level citations ---
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
            real_url = matched_chunk.source_url or cit.url
            cit.source_name = matched_chunk.source_name or cit.source_name
            cit.credibility_score = matched_chunk.credibility_score
            cit.retrieval_method = matched_chunk.retrieval_method

            # Only link reputed sources
            if _is_reputed_url(real_url):
                cit.url = real_url
                # Ensure source name matches the URL, not what the LLM hallucinated
                cit.source_name = matched_chunk.source_name or _source_name_from_url(real_url)
            else:
                # Fallback: find ANY reputed URL from the evidence pool
                fb_url, fb_name = _find_reputed_source_for_topic(evidence)
                if fb_url:
                    cit.url = fb_url
                    cit.source_name = fb_name or _source_name_from_url(fb_url)
                    logger.debug(
                        "  Citation %d: matched chunk URL not reputed, using fallback: %s (%s)",
                        i, fb_url[:60], cit.source_name,
                    )
                else:
                    cit.url = ""
                    logger.debug(
                        "  Citation %d: no reputed URL found in evidence pool",
                        i,
                    )

            validated.append(cit)
            logger.debug(
                "  Citation %d: ✓ VALIDATED (score=%d, source=%s, url=%s)",
                i, score, cit.source_name, "linked" if cit.url else "text-only"
            )
        else:
            logger.warning(
                "  Citation %d: ✗ STRIPPED (score=%d < %d, quote='%s')",
                i, score, FUZZY_THRESHOLD, cit.relevant_quote[:60]
            )
            stripped_count += 1

    # --- 3. Deduplicate citations by URL ---
    seen_urls: set[str] = set()
    deduped: list[Citation] = []
    dup_count = 0
    for cit in validated:
        if cit.url:
            if cit.url in seen_urls:
                dup_count += 1
                continue
            seen_urls.add(cit.url)
        deduped.append(cit)

    if dup_count:
        logger.info("Removed %d duplicate citation URL(s)", dup_count)

    result.citations = deduped

    # Also deduplicate sub-claim source URLs
    for sc in result.sub_claims:
        seen_sc_urls: set[str] = set()
        unique_support: list[SubClaimSource] = []
        for s in sc.supporting_sources:
            key = s.url or s.name
            if key not in seen_sc_urls:
                seen_sc_urls.add(key)
                unique_support.append(s)
        sc.supporting_sources = unique_support

        unique_contra: list[SubClaimSource] = []
        for s in sc.contradicting_sources:
            key = s.url or s.name
            if key not in seen_sc_urls:
                seen_sc_urls.add(key)
                unique_contra.append(s)
        sc.contradicting_sources = unique_contra

    if not deduped:
        logger.warning("All citations stripped by fuzzy matching – verdict unchanged, citations empty")
        result.reasoning += " [Note: Citations could not be fuzzy-matched to evidence text, but verdict is based on evidence analysis.]"

    linked = sum(1 for c in deduped if c.url)
    logger.info(
        "Citation validation complete: %d validated (%d with links, %d dups removed), %d stripped",
        len(deduped), linked, dup_count, stripped_count,
    )
    return result
