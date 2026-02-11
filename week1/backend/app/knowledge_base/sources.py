"""Source credibility scoring and domain classification."""

from __future__ import annotations

from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Domain → credibility map
# ---------------------------------------------------------------------------

# Tier 1: highest credibility (0.95)
_TIER1 = {
    "apnews.com", "reuters.com", "bbc.com", "bbc.co.uk",
    "nytimes.com", "washingtonpost.com", "wikipedia.org",
    "en.wikipedia.org", "nature.com", "science.org",
    "who.int", "cdc.gov", "nih.gov",
}

# Tier 2: high credibility (0.80)
_TIER2 = {
    "theguardian.com", "economist.com", "ft.com",
    "npr.org", "pbs.org", "politifact.com",
    "snopes.com", "factcheck.org", "fullfact.org",
    "bloomberg.com", "cnbc.com", "aljazeera.com",
}

# Tier 5: known unreliable (0.20)
_TIER5 = {
    "infowars.com", "naturalnews.com", "theonion.com",
    "babylonbee.com",
}

CREDIBILITY_MAP: dict[str, float] = {}
for d in _TIER1:
    CREDIBILITY_MAP[d] = 0.95
for d in _TIER2:
    CREDIBILITY_MAP[d] = 0.80
for d in _TIER5:
    CREDIBILITY_MAP[d] = 0.20


def extract_domain(url: str) -> str:
    """Return the bare domain from a URL."""
    try:
        host = urlparse(url).netloc.lower()
        # strip 'www.'
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


def score_source(url: str) -> float:
    """Return a credibility score (0-1) for a given URL."""
    domain = extract_domain(url)
    if not domain:
        return 0.40

    # exact match
    if domain in CREDIBILITY_MAP:
        return CREDIBILITY_MAP[domain]

    # check if it's a .gov or .edu domain → tier 2
    if domain.endswith(".gov") or domain.endswith(".edu"):
        return 0.80

    # default: unknown → 0.40
    return 0.40
