"""Live web search integration via Tavily API with caching and rate limiting."""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Optional

from app.config import settings
from app.models import EvidenceChunk
from app.knowledge_base.sources import score_source

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Simple in-memory cache
# ---------------------------------------------------------------------------

_cache: dict[str, tuple[float, list[EvidenceChunk]]] = {}  # key → (timestamp, results)


def _cache_key(query: str) -> str:
    return hashlib.sha256(query.strip().lower().encode()).hexdigest()[:32]


def _get_cached(query: str) -> Optional[list[EvidenceChunk]]:
    key = _cache_key(query)
    if key in _cache:
        ts, results = _cache[key]
        if time.time() - ts < settings.web_cache_ttl_seconds:
            logger.info("Web search cache hit for query")
            return results
        del _cache[key]
    return None


def _set_cache(query: str, results: list[EvidenceChunk]) -> None:
    _cache[_cache_key(query)] = (time.time(), results)


# ---------------------------------------------------------------------------
# Simple token-bucket rate limiter
# ---------------------------------------------------------------------------

_rate_tokens: float = 10.0
_rate_max: float = 10.0
_rate_refill: float = 10.0 / 60.0  # 10 tokens per minute
_rate_last: float = time.time()


def _rate_limit_acquire() -> bool:
    """Return True if a request is allowed, consuming one token."""
    global _rate_tokens, _rate_last
    now = time.time()
    elapsed = now - _rate_last
    _rate_last = now
    _rate_tokens = min(_rate_max, _rate_tokens + elapsed * _rate_refill)
    if _rate_tokens >= 1.0:
        _rate_tokens -= 1.0
        return True
    return False


# ---------------------------------------------------------------------------
# Tavily search
# ---------------------------------------------------------------------------

async def web_search(query: str, max_results: int | None = None) -> list[EvidenceChunk]:
    """Search the web for evidence related to *query*.

    Returns a list of EvidenceChunks sourced from live web results.
    """
    cached = _get_cached(query)
    if cached is not None:
        logger.debug("Web search cache HIT for query")
        return cached

    if not settings.tavily_api_key:
        logger.warning("TAVILY_API_KEY not set – skipping web search")
        return []

    if not _rate_limit_acquire():
        logger.warning("Web search rate-limited; returning empty results")
        return []

    n = max_results or settings.web_search_max_results
    logger.debug("Web search (Tavily) for: '%s' (max_results=%d)", query[:80], n)

    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=settings.tavily_api_key)
        response = client.search(
            query=query,
            search_depth="advanced",
            max_results=n,
            include_raw_content=False,
        )
    except Exception as exc:
        logger.error("Tavily search failed: %s", exc)
        return []

    results: list[EvidenceChunk] = []
    for item in response.get("results", []):
        url = item.get("url", "")
        text = item.get("content", "")
        if not text:
            continue
        results.append(
            EvidenceChunk(
                text=text,
                source_name=item.get("title", "Web"),
                source_url=url,
                publish_date=item.get("published_date", "unknown"),
                category="web",
                credibility_score=score_source(url),
                retrieval_method="web_search",
                relevance_score=item.get("score", 0.0),
            )
        )

    _set_cache(query, results)
    logger.debug("Web search returned %d results", len(results))
    return results
