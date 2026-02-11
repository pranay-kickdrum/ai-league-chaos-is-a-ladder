"""LLM-based claim extraction and decomposition."""

from __future__ import annotations

import json
import logging
from typing import Optional

from openai import OpenAI

from app.config import settings

logger = logging.getLogger(__name__)

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


# ---------------------------------------------------------------------------
# Claim extraction
# ---------------------------------------------------------------------------

EXTRACT_SYSTEM = """\
You are a claim-extraction assistant. Given raw text (a headline, snippet, or paragraph), \
extract the single most important factual claim that can be verified. \
Return ONLY the claim text, nothing else. \
If the text contains no verifiable factual claim, return "NO_CLAIM"."""


async def extract_claim(raw_text: str) -> str:
    """Extract the core verifiable claim from raw user-highlighted text."""
    logger.info("Extracting claim from %d characters of text", len(raw_text))
    client = _get_client()
    resp = client.chat.completions.create(
        model=settings.fast_llm_model,
        messages=[
            {"role": "system", "content": EXTRACT_SYSTEM},
            {"role": "user", "content": raw_text.strip()},
        ],
        temperature=0.0,
        max_tokens=256,
    )
    claim = resp.choices[0].message.content.strip()
    
    if claim == "NO_CLAIM":
        logger.warning("LLM returned NO_CLAIM - no verifiable assertion found")
    else:
        logger.info("✓ Claim extracted: '%s'", claim[:150] + ("..." if len(claim) > 150 else ""))
    
    return claim


# ---------------------------------------------------------------------------
# Claim decomposition into sub-claims
# ---------------------------------------------------------------------------

DECOMPOSE_SYSTEM = """\
You are a claim-decomposition assistant. Given a factual claim, break it into a list of \
independent, atomic sub-claims that can each be verified separately.

Rules:
- Each sub-claim must be a single, simple factual statement.
- Preserve all numbers, dates, names exactly.
- If the claim is already atomic, return it as a single-item list.
- Return ONLY a JSON array of strings, e.g. ["sub-claim 1", "sub-claim 2"].
- No explanation, no markdown – just the JSON array."""


async def decompose_claim(claim: str) -> list[str]:
    """Split a compound claim into atomic verifiable sub-claims."""
    logger.info("Decomposing claim: '%s'", claim[:100])
    client = _get_client()
    resp = client.chat.completions.create(
        model=settings.fast_llm_model,
        messages=[
            {"role": "system", "content": DECOMPOSE_SYSTEM},
            {"role": "user", "content": claim},
        ],
        temperature=0.0,
        max_tokens=512,
    )
    raw = resp.choices[0].message.content.strip()

    try:
        sub_claims = json.loads(raw)
        if isinstance(sub_claims, list) and all(isinstance(s, str) for s in sub_claims):
            logger.info("✓ Decomposed into %d sub-claim(s)", len(sub_claims))
            return sub_claims
    except json.JSONDecodeError:
        logger.warning("Failed to parse LLM decomposition output as JSON")

    # Fallback: treat the whole claim as a single sub-claim
    logger.info("Using original claim as single sub-claim (decomposition failed)")
    return [claim]
