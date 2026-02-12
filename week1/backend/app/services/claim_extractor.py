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
You are a claim-extraction assistant. Given raw text (a headline, snippet, paragraph, \
or even informal / poorly-formatted text), extract the single most important factual \
claim that can be verified.

IMPORTANT RULES:
- Fix grammar, spelling, and casing issues in the extracted claim. Produce a clean, \
  well-formed sentence regardless of how the input was written.
- Be GENEROUS in what you consider a verifiable claim. If the text contains ANY assertion \
  about facts, statistics, events, people, or the world, extract it.
- Interpret informal language, slang, abbreviations, and rhetorical questions as claims \
  when they imply a factual assertion. For example:
  - "no way tesla made 10B last quarter" → "Tesla made $10 billion in revenue last quarter"
  - "earth is flat lol" → "The Earth is flat"
  - "biden is the oldest president ever" → "Joe Biden is the oldest president in US history"
- Only return "NO_CLAIM" if the text is purely an opinion with zero factual assertions, \
  a greeting, or completely unintelligible.
- Return ONLY the cleaned-up claim text, nothing else."""


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
independent, atomic sub-claims that can each be verified separately using search engines \
and knowledge bases.

Rules:
- Each sub-claim must be a single, simple factual statement.
- Preserve all numbers, dates, names exactly.
- Make each sub-claim SEARCH-FRIENDLY: write them as clear, self-contained statements \
  that would make good search queries. Include key entities, dates, and specific details.
- If the claim mentions a person, include their full name and relevant title/role.
- If the claim mentions a statistic, include the metric, value, time period, and entity.
- If the claim is already atomic, still return it PLUS 1-2 rephrased search variants. \
  For example, for "Tesla revenue was $10B in Q3 2024", return:
  ["Tesla revenue was $10 billion in Q3 2024", "Tesla quarterly earnings Q3 2024 revenue"]
- Always return at least 2 items to improve retrieval coverage.
- Return ONLY a JSON array of strings, e.g. ["sub-claim 1", "search variant 1"].
- No explanation, no markdown – just the JSON array."""


async def decompose_claim(claim: str) -> list[str]:
    """Split a compound claim into atomic verifiable sub-claims with search variants."""
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
            logger.info("✓ Decomposed into %d sub-claim(s)/search variants", len(sub_claims))
            return sub_claims
    except json.JSONDecodeError:
        logger.warning("Failed to parse LLM decomposition output as JSON")

    # Fallback: use original claim + a simplified keyword version
    logger.info("Using original claim + keyword variant as fallback")
    # Generate a keyword-style search query from the claim
    keywords = " ".join(w for w in claim.split() if len(w) > 3)[:150]
    return [claim, keywords] if keywords != claim else [claim]
