"""Cross-encoder reranker using sentence-transformers."""

from __future__ import annotations

import logging
import math
from typing import Optional

from app.config import settings
from app.models import EvidenceChunk

logger = logging.getLogger(__name__)


def _sigmoid(x: float) -> float:
    """Convert raw cross-encoder logit to a 0-1 probability."""
    try:
        return 1.0 / (1.0 + math.exp(-x))
    except OverflowError:
        return 0.0 if x < 0 else 1.0

_model = None

MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"


def warmup_model():
    """Eagerly load the cross-encoder model (call at server startup)."""
    _get_model()


def _get_model():
    """Lazy-load the cross-encoder model from local cache (no HuggingFace Hub checks)."""
    global _model
    if _model is None:
        import os
        from sentence_transformers import CrossEncoder

        # Skip all HuggingFace Hub HTTP calls -- use local cache only
        # The model is already downloaded (~80 MB), no need to check for updates
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"

        try:
            _model = CrossEncoder(MODEL_NAME, local_files_only=True)
            logger.info("Loaded cross-encoder model from local cache: %s", MODEL_NAME)
        except Exception:
            # First run ever -- need to download, so go online
            logger.info("Model not in cache, downloading from HuggingFace Hub...")
            os.environ.pop("HF_HUB_OFFLINE", None)
            os.environ.pop("TRANSFORMERS_OFFLINE", None)
            _model = CrossEncoder(MODEL_NAME)
            logger.info("Downloaded and loaded cross-encoder model: %s", MODEL_NAME)
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

    # Normalise raw logits → 0-1 probabilities with sigmoid.
    # ms-marco-MiniLM-L-6-v2 outputs raw logits in ~[-12, +12]; sigmoid
    # maps 0 → 0.5 (decision boundary), giving downstream code a consistent
    # 0-1 scale for sufficiency thresholds.
    norm_scores = [_sigmoid(float(s)) for s in scores]

    scored = list(zip(chunks, norm_scores))
    scored.sort(key=lambda x: x[1], reverse=True)

    result: list[EvidenceChunk] = []
    for chunk, score in scored[:k]:
        chunk.relevance_score = score
        result.append(chunk)

    logger.debug(
        "Reranking complete: top score=%.3f, kept %d/%d chunks",
        result[0].relevance_score if result else 0.0,
        len(result),
        len(chunks),
    )
    return result
