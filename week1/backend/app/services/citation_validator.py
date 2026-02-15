"""Post-hoc citation validation – deduplicates and cleans citations.

Citations are now built programmatically from evidence chunks (not from LLM
output), so this module only needs to deduplicate and validate URLs.
"""

from __future__ import annotations

import logging

from app.models import Citation, EvidenceChunk, SubClaimSource, VerifyResponse

logger = logging.getLogger(__name__)


def _is_valid_url(url: str) -> bool:
    """Return True if the URL is a real, specific article link (not just a domain root)."""
    if not url or not url.startswith(("http://", "https://")):
        return False
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        if not path or len(path) < 5:
            return False
    except Exception:
        pass
    return True


async def validate_citations(
    result: VerifyResponse,
    evidence: list[EvidenceChunk],
) -> VerifyResponse:
    """Validate citations in the verification result.

    Since citations are now built from real evidence (not LLM output),
    this only needs to:
    1. Filter out citations with invalid / missing URLs
    2. Deduplicate by URL
    3. Deduplicate sub-claim sources
    """
    # --- 1. Filter citations — keep those with a valid URL ---
    valid: list[Citation] = []
    no_url_count = 0
    for cit in result.citations:
        if _is_valid_url(cit.url):
            valid.append(cit)
        else:
            no_url_count += 1
            logger.debug("  Dropping citation without valid URL: %s", cit.source_name)

    # --- 2. Deduplicate citations by URL ---
    seen_urls: set[str] = set()
    deduped: list[Citation] = []
    dup_count = 0
    for cit in valid:
        if cit.url in seen_urls:
            dup_count += 1
            continue
        seen_urls.add(cit.url)
        deduped.append(cit)

    result.citations = deduped

    # --- 3. Deduplicate sub-claim sources ---
    for sc in result.sub_claims:
        seen_sc: set[str] = set()
        unique_support: list[SubClaimSource] = []
        for s in sc.supporting_sources:
            key = s.url or s.name
            if key not in seen_sc:
                seen_sc.add(key)
                unique_support.append(s)
        sc.supporting_sources = unique_support

        unique_contra: list[SubClaimSource] = []
        for s in sc.contradicting_sources:
            key = s.url or s.name
            if key not in seen_sc:
                seen_sc.add(key)
                unique_contra.append(s)
        sc.contradicting_sources = unique_contra

    logger.info(
        "Citation validation: %d valid (%d no-url dropped, %d dups removed)",
        len(deduped), no_url_count, dup_count,
    )
    return result
