"""Cross-encoder reranker using sentence-transformers."""

from __future__ import annotations

import logging
from typing import Optional

from app.config import settings
from app.models import EvidenceChunk

logger = logging.getLogger(__name__)

_model = None

MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"


def _get_model():
    """Lazy-load the cross-encoder model (first call downloads ~80 MB)."""
    global _model
    if _model is None:
        from sentence_transformers import CrossEncoder

        _model = CrossEncoder(MODEL_NAME)
        logger.info("Loaded cross-encoder model: %s", MODEL_NAME)
    return _model


async def rerank(
    query: str,
    chunks: list[EvidenceChunk],
    top_k: Optional[int] = None,
) -> list[EvidenceChunk]:
    """Rerank *chunks* by relevance to *query* using a cross-encoder.

    Returns the top-k chunks sorted by cross-encoder score (descending).
    """
    if not chunks:
        return []

    k = top_k or settings.rerank_top_k
    logger.debug("Reranking %d chunks → top-%d", len(chunks), k)
    
    model = _get_model()

    pairs = [(query, c.text) for c in chunks]
    scores = model.predict(pairs)

    scored = list(zip(chunks, scores))
    scored.sort(key=lambda x: x[1], reverse=True)

    result: list[EvidenceChunk] = []
    for chunk, score in scored[:k]:
        chunk.relevance_score = float(score)
        result.append(chunk)

    logger.debug(
        "Reranking complete: top score=%.3f, kept %d/%d chunks",
        result[0].relevance_score if result else 0.0,
        len(result),
        len(chunks),
    )
    return result
