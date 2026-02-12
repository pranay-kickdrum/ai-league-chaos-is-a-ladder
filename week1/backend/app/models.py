"""Pydantic models for request/response and internal data structures."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Verdict(str, Enum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    MISLEADING = "MISLEADING"
    NOT_ENOUGH_EVIDENCE = "NOT_ENOUGH_EVIDENCE"


# ---------------------------------------------------------------------------
# Internal data structures
# ---------------------------------------------------------------------------

class EvidenceChunk(BaseModel):
    """A single retrieved evidence passage with metadata."""
    text: str
    source_name: str = "Unknown"
    source_url: str = ""
    publish_date: str = "unknown"
    category: str = "unknown"
    credibility_score: float = 0.4
    retrieval_method: str = "knowledge_base"  # or "web_search"
    relevance_score: float = 0.0


class Citation(BaseModel):
    """A verified citation attached to the final output."""
    source_name: str
    url: str
    publish_date: str = "unknown"
    relevant_quote: str
    credibility_score: float = 0.0
    retrieval_method: str = "knowledge_base"


class SubClaimSource(BaseModel):
    """A source linked to a sub-claim verdict."""
    name: str
    url: str = ""
    summary: str = ""


class SubClaimResult(BaseModel):
    """Verification result for a single sub-claim."""
    text: str
    verdict: Verdict = Verdict.NOT_ENOUGH_EVIDENCE
    evidence_summary: str = ""
    supporting_sources: list[SubClaimSource] = Field(default_factory=list)
    contradicting_sources: list[SubClaimSource] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# API request / response
# ---------------------------------------------------------------------------

class VerifyRequest(BaseModel):
    """Incoming verification request."""
    text: str = Field(..., min_length=1, description="The text to verify")
    url: Optional[str] = Field(None, description="Source page URL for context")


class VerifyResponse(BaseModel):
    """Final verification response returned to the client."""
    claim: str
    verdict: Verdict
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    sub_claims: list[SubClaimResult] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Internal LLM structured output
# ---------------------------------------------------------------------------

class LLMVerificationOutput(BaseModel):
    """Expected JSON structure from the LLM verification prompt."""
    sub_claims: list[dict] = Field(default_factory=list)
    verdict: str = "NOT_ENOUGH_EVIDENCE"
    confidence: float = 0.0
    reasoning: str = ""
    citations: list[dict] = Field(default_factory=list)
