"""LLM-based claim extraction and decomposition."""

from __future__ import annotations

import json
import logging
from typing import Optional

from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

_client: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


# ---------------------------------------------------------------------------
# Claim extraction
# ---------------------------------------------------------------------------

EXTRACT_AND_DECOMPOSE_SYSTEM = """\
You are a claim-extraction and decomposition assistant. Given raw text (a headline, \
snippet, paragraph, or even informal / poorly-formatted text), do TWO things in one step:

1. EXTRACT the single most important factual claim that can be verified.
2. DECOMPOSE it into sub-claims ONLY if the claim is genuinely compound (contains \
   multiple independent facts that need separate verification).

EXTRACTION RULES:
- Fix grammar, spelling, and casing issues. Produce a clean, well-formed sentence.
- Be GENEROUS in what you consider a verifiable claim.
- Interpret informal language, slang, abbreviations as claims when they imply a factual \
  assertion (e.g. "no way tesla made 10B" → "Tesla made $10 billion in revenue").
- Only set claim to "NO_CLAIM" if the text has zero factual assertions.

DECOMPOSITION RULES:
- ONLY decompose if the claim contains 2+ GENUINELY DIFFERENT facts to verify.
  Example that SHOULD be decomposed:
    "Tesla's revenue was $25B in Q3 2024 and Elon Musk is the richest person in the world"
    → ["Tesla's revenue was $25 billion in Q3 2024", "Elon Musk is the richest person in the world"]
  Example that should NOT be decomposed (single fact):
    "The Earth is approximately 4.5 billion years old"
    → ["The Earth is approximately 4.5 billion years old"]
- Do NOT create rephrased variants or search-style rewrites of the same fact. \
  Two sub-claims meaning the same thing is a waste.
- If the claim is already a single atomic fact, return it as a single-item list.
- Each sub-claim must be a self-contained, search-friendly factual statement.
- Preserve all numbers, dates, names exactly.

RESPOND IN THIS EXACT JSON FORMAT (no markdown, just raw JSON):
{"claim": "the cleaned-up claim", "sub_claims": ["sub-claim 1"]}

If no claim found: {"claim": "NO_CLAIM", "sub_claims": []}"""


async def extract_and_decompose(raw_text: str) -> tuple[str, list[str]]:
    """Extract claim and decompose into sub-claims in a SINGLE LLM call."""
    logger.info("Extracting + decomposing from %d characters of text", len(raw_text))
    client = _get_client()
    resp = await client.chat.completions.create(
        model=settings.fast_llm_model,
        messages=[
            {"role": "system", "content": EXTRACT_AND_DECOMPOSE_SYSTEM},
            {"role": "user", "content": raw_text.strip()},
        ],
        temperature=0.0,
        max_tokens=512,
    )
    raw = resp.choices[0].message.content.strip()

    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
    if raw.endswith("```"):
        raw = raw.rsplit("```", 1)[0]
    raw = raw.strip()

    try:
        parsed = json.loads(raw)
        claim = parsed.get("claim", "").strip()
        sub_claims = parsed.get("sub_claims", [])

        if claim and claim != "NO_CLAIM" and isinstance(sub_claims, list) and sub_claims:
            logger.info("✓ Extracted claim: '%s'", claim[:150])
            logger.info("✓ Decomposed into %d sub-claim(s)", len(sub_claims))
            return claim, sub_claims

        if claim == "NO_CLAIM":
            logger.warning("LLM returned NO_CLAIM - no verifiable assertion found")
            return "NO_CLAIM", []

    except (json.JSONDecodeError, Exception) as exc:
        logger.warning("Failed to parse combined extract+decompose output: %s", exc)

    # Fallback: use the raw text as a single claim (no artificial decomposition)
    logger.info("Fallback: using raw text as single claim")
    fallback_claim = raw_text.strip()[:500]
    return fallback_claim, [fallback_claim]


# Keep legacy functions for backward compatibility
async def extract_claim(raw_text: str) -> str:
    """Extract the core verifiable claim from raw user-highlighted text."""
    claim, _ = await extract_and_decompose(raw_text)
    return claim


async def decompose_claim(claim: str) -> list[str]:
    """Split a compound claim into atomic verifiable sub-claims."""
    _, sub_claims = await extract_and_decompose(claim)
    return sub_claims if sub_claims else [claim]
