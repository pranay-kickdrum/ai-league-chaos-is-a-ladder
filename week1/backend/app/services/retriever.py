"""Hybrid retriever: dense (ChromaDB) + sparse (BM25) with Reciprocal Rank Fusion."""

from __future__ import annotations

import json as _json
import logging
from typing import Optional

from rank_bm25 import BM25Okapi

from app.config import settings
from app.models import EvidenceChunk
from app.services.embedder import batch_query_collection, embed_query, get_collection, query_collection
from app.knowledge_base.sources import score_source

logger = logging.getLogger(__name__)


def _resolve_source_url(meta: dict) -> str:
    """Return the best available URL for an evidence chunk.

    For regular web evidence, ``source_url`` is already set.
    For *Verified Claim (System)* entries, ``source_url`` is empty but the
    real citation URLs are stored in the ``citation_urls`` metadata field
    (a JSON-encoded list of ``{source_name, url}`` dicts).  We extract the
    first valid URL from that list so it can be surfaced to the LLM and the
    user.
    """
    url = meta.get("source_url", "")
    if url:
        return url

    # Fallback: extract from citation_urls (verified-claim entries)
    raw = meta.get("citation_urls", "")
    if raw:
        try:
            entries = _json.loads(raw) if isinstance(raw, str) else raw
            for entry in entries:
                if isinstance(entry, dict) and entry.get("url"):
                    return entry["url"]
        except (ValueError, TypeError):
            pass
    return ""


def _resolve_source_name(meta: dict) -> str:
    """Return a descriptive display name for an evidence source.

    The credibility score is NOT embedded in the name — the frontend
    renders it separately as a badge to avoid duplication.
    """
    return meta.get("source_name", "Unknown")


# ---------------------------------------------------------------------------
# BM25 index (built lazily from ChromaDB contents)
# ---------------------------------------------------------------------------

_bm25_index: Optional[BM25Okapi] = None
_bm25_corpus_docs: list[dict] = []  # parallel list of {text, metadata}
_bm25_corpus_size: int = 0


def warmup_bm25_index() -> None:
    """Eagerly build the BM25 index (call at server startup)."""
    _get_bm25()


def _rebuild_bm25_index() -> None:
    """Rebuild the BM25 index from all documents in ChromaDB."""
    global _bm25_index, _bm25_corpus_docs, _bm25_corpus_size

    logger.info("  [BM25 Index] Building BM25 index from ChromaDB...")
    
    collection = get_collection()
    count = collection.count()
    if count == 0:
        logger.warning("  [BM25 Index] ChromaDB is empty – BM25 index will be empty")
        _bm25_index = None
        _bm25_corpus_docs = []
        _bm25_corpus_size = 0
        return

    # Fetch all documents (ChromaDB paginates at ~10k by default)
    all_docs = collection.get(include=["documents", "metadatas"])
    texts = all_docs["documents"] or []
    metas = all_docs["metadatas"] or [{} for _ in texts]

    logger.info("  [BM25 Index] Tokenizing %d documents...", len(texts))
    tokenized = [t.lower().split() for t in texts]
    _bm25_index = BM25Okapi(tokenized)
    _bm25_corpus_docs = [
        {"text": t, "metadata": m} for t, m in zip(texts, metas)
    ]
    _bm25_corpus_size = count
    logger.info("  [BM25 Index] ✓ Index built: %d documents indexed", count)


def _get_bm25() -> tuple[Optional[BM25Okapi], list[dict]]:
    """Return the current BM25 index, rebuilding if needed."""
    collection = get_collection()
    current_count = collection.count()
    if _bm25_index is None or current_count != _bm25_corpus_size:
        _rebuild_bm25_index()
    return _bm25_index, _bm25_corpus_docs


# ---------------------------------------------------------------------------
# Reciprocal Rank Fusion
# ---------------------------------------------------------------------------

def reciprocal_rank_fusion(
    ranked_lists: list[list[dict]],
    k: int = 60,
) -> list[dict]:
    """Merge multiple ranked lists using RRF.

    Each list item must have a ``text`` key (used for de-duplication).
    Returns a single list sorted by fused score (descending).
    """
    scores: dict[str, float] = {}
    doc_map: dict[str, dict] = {}

    for ranked in ranked_lists:
        for rank, doc in enumerate(ranked):
            key = doc["text"][:200]  # use first 200 chars as dedup key
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
            if key not in doc_map:
                doc_map[key] = doc

    sorted_keys = sorted(scores, key=scores.get, reverse=True)  # type: ignore[arg-type]
    return [doc_map[k] for k in sorted_keys]


# ---------------------------------------------------------------------------
# Dense retrieval
# ---------------------------------------------------------------------------

def _dense_retrieve(
    query: str,
    top_k: int,
    where: Optional[dict] = None,
    query_embedding: Optional[list[float]] = None,
) -> list[dict]:
    """Return top-k results from ChromaDB dense vector search."""
    if query_embedding is not None:
        query_emb = query_embedding
        logger.debug("  [Dense Search] Using pre-computed embedding")
    else:
        logger.debug("  [Dense Search] Embedding query...")
        query_emb = embed_query(query)
    logger.debug("  [Dense Search] Querying ChromaDB for top-%d matches...", top_k)
    
    results = query_collection(query_emb, n_results=top_k, where=where)

    docs: list[dict] = []
    if not results or not results.get("documents"):
        logger.debug("  [Dense Search] No results found")
        return docs

    for text, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        docs.append({"text": text, "metadata": meta, "score": 1.0 - dist})
    
    logger.debug("  [Dense Search] Retrieved %d results (top score: %.3f)", 
                len(docs), docs[0]["score"] if docs else 0.0)
    return docs


# ---------------------------------------------------------------------------
# Sparse (BM25) retrieval
# ---------------------------------------------------------------------------

def _bm25_retrieve(query: str, top_k: int) -> list[dict]:
    """Return top-k results from the BM25 index."""
    bm25, corpus = _get_bm25()
    if bm25 is None or not corpus:
        logger.debug("  [BM25 Search] Index not available")
        return []

    logger.debug("  [BM25 Search] Tokenizing query and searching...")
    tokens = query.lower().split()
    scores = bm25.get_scores(tokens)

    ranked_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
    results: list[dict] = []
    for idx in ranked_indices:
        if scores[idx] <= 0:
            break
        results.append({
            "text": corpus[idx]["text"],
            "metadata": corpus[idx]["metadata"],
            "score": float(scores[idx]),
        })
    
    logger.debug("  [BM25 Search] Retrieved %d results (top score: %.3f)", 
                len(results), results[0]["score"] if results else 0.0)
    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def hybrid_retrieve(
    query: str,
    dense_top_k: int | None = None,
    bm25_top_k: int | None = None,
    where: Optional[dict] = None,
    query_embedding: Optional[list[float]] = None,
) -> list[EvidenceChunk]:
    """Run hybrid retrieval and return merged, de-duplicated EvidenceChunks.

    If *query_embedding* is provided the dense branch skips the OpenAI call
    (useful when embeddings were batch-computed upfront).
    """
    dk = dense_top_k or settings.dense_top_k
    bk = bm25_top_k or settings.bm25_top_k

    logger.debug("  [Hybrid Retrieval] Query: '%s'", query[:80])
    logger.debug("  [Hybrid Retrieval] Running parallel: Dense (top-%d) + BM25 (top-%d)", dk, bk)
    
    dense_results = _dense_retrieve(query, dk, where=where, query_embedding=query_embedding)
    bm25_results = _bm25_retrieve(query, bk)

    logger.debug("  [Hybrid Retrieval] Applying Reciprocal Rank Fusion (k=%d)...", settings.rrf_k)
    merged = reciprocal_rank_fusion([dense_results, bm25_results], k=settings.rrf_k)

    chunks: list[EvidenceChunk] = []
    for doc in merged:
        meta = doc.get("metadata", {})
        url = _resolve_source_url(meta)
        chunks.append(
            EvidenceChunk(
                text=doc["text"],
                source_name=_resolve_source_name(meta),
                source_url=url,
                publish_date=meta.get("publish_date", "unknown"),
                category=meta.get("category", "unknown"),
                credibility_score=meta.get("credibility_score", score_source(url)),
                retrieval_method="knowledge_base",
                relevance_score=doc.get("score", 0.0),
            )
        )
    logger.debug(
        "  [Hybrid Retrieval] Fusion complete: %d dense + %d bm25 → %d merged",
        len(dense_results),
        len(bm25_results),
        len(chunks),
    )
    return chunks


async def batch_hybrid_retrieve(
    queries: list[str],
    query_embeddings: list[list[float]],
    dense_top_k: int | None = None,
    bm25_top_k: int | None = None,
) -> list[list[EvidenceChunk]]:
    """Retrieve evidence for *multiple* queries in a single batched operation.

    1. ONE ChromaDB call with all embeddings (biggest win).
    2. Per-query BM25 search (local, fast – no benefit from batching).
    3. Per-query RRF fusion.

    Returns a list of EvidenceChunk lists, one per input query.
    """
    if not queries:
        return []

    dk = dense_top_k or settings.dense_top_k
    bk = bm25_top_k or settings.bm25_top_k

    logger.info(
        "  [Batch Retrieval] %d queries, Dense top-%d, BM25 top-%d",
        len(queries), dk, bk,
    )

    # --- 1. ONE batched ChromaDB dense query ---------------------------------
    batch_raw = batch_query_collection(query_embeddings, n_results=dk)

    # Parse each query's raw ChromaDB results into doc dicts
    all_dense: list[list[dict]] = []
    for i, raw in enumerate(batch_raw):
        docs: list[dict] = []
        if raw.get("documents") and raw["documents"][0]:
            for text, meta, dist in zip(
                raw["documents"][0],
                raw["metadatas"][0],
                raw["distances"][0],
            ):
                docs.append({"text": text, "metadata": meta, "score": 1.0 - dist})
        all_dense.append(docs)
        logger.debug("    Query %d dense: %d results", i + 1, len(docs))

    # --- 2. Per-query BM25 (local, fast) ------------------------------------
    all_bm25: list[list[dict]] = []
    for i, q in enumerate(queries):
        bm25_results = _bm25_retrieve(q, bk)
        all_bm25.append(bm25_results)
        logger.debug("    Query %d BM25: %d results", i + 1, len(bm25_results))

    # --- 3. Per-query RRF fusion → EvidenceChunks ----------------------------
    all_chunks: list[list[EvidenceChunk]] = []
    for i, (dense_results, bm25_results) in enumerate(zip(all_dense, all_bm25)):
        merged = reciprocal_rank_fusion([dense_results, bm25_results], k=settings.rrf_k)
        chunks: list[EvidenceChunk] = []
        for doc in merged:
            meta = doc.get("metadata", {})
            url = _resolve_source_url(meta)
            chunks.append(
                EvidenceChunk(
                    text=doc["text"],
                    source_name=_resolve_source_name(meta),
                    source_url=url,
                    publish_date=meta.get("publish_date", "unknown"),
                    category=meta.get("category", "unknown"),
                    credibility_score=meta.get("credibility_score", score_source(url)),
                    retrieval_method="knowledge_base",
                    relevance_score=doc.get("score", 0.0),
                )
            )
        all_chunks.append(chunks)
        logger.debug(
            "    Query %d fused: %d dense + %d bm25 → %d merged",
            i + 1, len(dense_results), len(bm25_results), len(chunks),
        )

    logger.info(
        "  [Batch Retrieval] Done: %s chunks per query",
        [len(c) for c in all_chunks],
    )
    return all_chunks
