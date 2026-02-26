"""In-memory TTL cache to reduce API calls."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Optional

from cachetools import TTLCache

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Global cache instance
_cache: TTLCache = TTLCache(
    maxsize=settings.CACHE_MAX_SIZE,
    ttl=settings.CACHE_TTL_SECONDS,
)


def _make_key(query_type: str, **params: Any) -> str:
    """Deterministic cache key from query type + sorted params."""
    raw = json.dumps({"t": query_type, **params}, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def cache_get(query_type: str, **params: Any) -> Optional[Any]:
    """Return cached result or None."""
    key = _make_key(query_type, **params)
    result = _cache.get(key)
    if result is not None:
        logger.debug("Cache HIT: %s %s", query_type, key[:8])
    return result


def cache_set(query_type: str, value: Any, **params: Any) -> None:
    """Store a result in the cache."""
    key = _make_key(query_type, **params)
    _cache[key] = value
    logger.debug("Cache SET: %s %s", query_type, key[:8])


def cache_clear() -> None:
    """Clear the entire cache."""
    _cache.clear()
    logger.info("Cache cleared")
