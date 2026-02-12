"""Claim extraction and decomposition – heuristic-first, LLM fallback."""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

_client: Optional[AsyncOpenAI] = None

# Thresholds for heuristic path
_SHORT_TEXT_LIMIT = 300          # characters – below this, skip the LLM
_MAX_SENTENCES_FOR_HEURISTIC = 3  # up to 3 sentences → heuristic is fine

# Conjunctions / clause boundaries used to split compound claims
_SPLIT_PATTERN = re.compile(
    r"\s+(?:and|but|while|whereas|however|also|meanwhile|additionally)\s+",
    re.IGNORECASE,
)


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


# ---------------------------------------------------------------------------
# Lightweight text cleanup (no LLM needed)
# ---------------------------------------------------------------------------

def _clean_text(text: str) -> str:
    """Basic cleanup: strip whitespace, collapse spaces, remove stray quotes."""
    text = text.strip().strip('"').strip("'").strip()
    text = re.sub(r"\s+", " ", text)
    # Capitalize first letter if lowercase
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    # Ensure it ends with a period if it doesn't end with punctuation
    if text and text[-1] not in ".!?":
        text += "."
    return text


def _split_sentences(text: str) -> list[str]:
    """Simple sentence splitter."""
    # Split on period/exclamation/question followed by space + uppercase letter
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
    return [p.strip() for p in parts if p.strip()]


def _decompose_heuristic(claim: str) -> list[str]:
    """Split a compound claim on conjunctions into sub-claims.

    Only splits if the resulting parts each look like standalone facts
    (contain at least 5 words). Otherwise returns the claim as-is.
    """
    parts = _SPLIT_PATTERN.split(claim)
    # Filter: each part must be a meaningful statement (>= 5 words)
    valid = [_clean_text(p) for p in parts if len(p.split()) >= 5]

    if len(valid) >= 2:
        return valid
    return [claim]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def extract_and_decompose(raw_text: str) -> tuple[str, list[str]]:
    """Extract claim and decompose into sub-claims.

    FAST PATH (heuristic): For short inputs (≤ 300 chars / ≤ 3 sentences),
    skip the LLM entirely — clean up the text, split on conjunctions.

    SLOW PATH (LLM): For longer / complex multi-paragraph text, use the
    LLM to extract the main claim from an article.
    """
    text = raw_text.strip()
    sentences = _split_sentences(text)

    # --- Fast path: short input → heuristic ---
    if len(text) <= _SHORT_TEXT_LIMIT and len(sentences) <= _MAX_SENTENCES_FOR_HEURISTIC:
        logger.info("FAST PATH: Input is short (%d chars, %d sentences) – using heuristic",
                     len(text), len(sentences))
        claim = _clean_text(text)
        sub_claims = _decompose_heuristic(claim)
        logger.info("  Claim: '%s'", claim[:150])
        logger.info("  Sub-claims: %d", len(sub_claims))
        return claim, sub_claims

    # --- Slow path: long / complex input → LLM ---
    logger.info("SLOW PATH: Input is long (%d chars, %d sentences) – using LLM",
                 len(text), len(sentences))
    return await _llm_extract_and_decompose(text)


# ---------------------------------------------------------------------------
# LLM-based extraction (only for long / complex text)
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
- Do NOT create rephrased variants or search-style rewrites of the same fact.
- If the claim is already a single atomic fact, return it as a single-item list.
- Each sub-claim must be a self-contained, search-friendly factual statement.
- Preserve all numbers, dates, names exactly.

RESPOND IN THIS EXACT JSON FORMAT (no markdown, just raw JSON):
{"claim": "the cleaned-up claim", "sub_claims": ["sub-claim 1"]}

If no claim found: {"claim": "NO_CLAIM", "sub_claims": []}"""


async def _llm_extract_and_decompose(raw_text: str) -> tuple[str, list[str]]:
    """LLM-based extraction + decomposition for long/complex text."""
    logger.info("Extracting + decomposing from %d characters of text via LLM", len(raw_text))
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
