"""Embedding service using OpenAI text-embedding-3-small + ChromaDB storage."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.config import Settings as ChromaSettings
from openai import OpenAI

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OpenAI embedding helper
# ---------------------------------------------------------------------------

_openai_client: Optional[OpenAI] = None


def _get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=settings.openai_api_key)
    return _openai_client


def embed_texts(texts: list[str], batch_size: int = 10) -> list[list[float]]:
    """Embed a list of texts using OpenAI. Returns list of float vectors."""
    logger.info("=" * 60)
    logger.info("EMBEDDING GENERATION")
    logger.info("=" * 60)
    logger.info("Total texts to embed: %d", len(texts))
    logger.info("Batch size: %d", batch_size)
    logger.info("Model: %s (dimension: %d)", settings.embedding_model, settings.embedding_dimensions)
    
    client = _get_openai_client()
    all_embeddings: list[list[float]] = []
    num_batches = -(-len(texts) // batch_size)  # ceiling division
    
    for i in range(0, len(texts), batch_size):
        batch_num = (i // batch_size) + 1
        batch = texts[i : i + batch_size]
        
        logger.info("Processing batch %d/%d (%d texts)...", batch_num, num_batches, len(batch))
        
        resp = client.embeddings.create(
            model=settings.embedding_model,
            input=batch,
        )
        
        batch_embeddings = [d.embedding for d in resp.data]
        all_embeddings.extend(batch_embeddings)
        
        logger.info("  ✓ Batch %d complete: generated %d embeddings", batch_num, len(batch_embeddings))
    
    logger.info("=" * 60)
    logger.info("EMBEDDING COMPLETE: %d vectors generated", len(all_embeddings))
    logger.info("=" * 60)
    return all_embeddings


def embed_query(text: str) -> list[float]:
    """Embed a single query string."""
    logger.debug("Embedding query: '%s'", text[:100] + ("..." if len(text) > 100 else ""))
    embedding = embed_texts([text])[0]
    logger.debug("Query embedded: vector dimension=%d", len(embedding))
    return embedding


# ---------------------------------------------------------------------------
# ChromaDB collection management
# ---------------------------------------------------------------------------

_chroma_client: Optional[chromadb.ClientAPI] = None
_collection: Optional[chromadb.Collection] = None


def _get_chroma_client() -> chromadb.ClientAPI:
    global _chroma_client
    if _chroma_client is None:
        persist_dir = Path(settings.chroma_persist_dir)
        persist_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info("-" * 60)
        logger.info("INITIALIZING CHROMADB CLIENT")
        logger.info("-" * 60)
        logger.info("Persist directory: %s", persist_dir)
        logger.info("Directory exists: %s", persist_dir.exists())
        
        _chroma_client = chromadb.PersistentClient(
            path=str(persist_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        
        logger.info("✓ ChromaDB client initialized successfully")
        logger.info("-" * 60)
    return _chroma_client


def get_collection() -> chromadb.Collection:
    """Return (or create) the knowledge-base collection."""
    global _collection
    if _collection is None:
        logger.info("-" * 60)
        logger.info("LOADING KNOWLEDGE BASE COLLECTION")
        logger.info("-" * 60)
        
        client = _get_chroma_client()
        
        logger.info("Collection name: '%s'", settings.chroma_collection_name)
        logger.info("Similarity metric: cosine")
        
        _collection = client.get_or_create_collection(
            name=settings.chroma_collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        
        doc_count = _collection.count()
        logger.info("✓ Collection loaded: %d documents in knowledge base", doc_count)
        
        if doc_count == 0:
            logger.warning("⚠ Knowledge base is EMPTY - no documents indexed yet")
            logger.warning("  Run: python scripts/ingest_kb.py --liar")
        
        logger.info("-" * 60)
    return _collection


def add_documents(
    ids: list[str],
    texts: list[str],
    embeddings: list[list[float]],
    metadatas: list[dict],
) -> None:
    """Add documents to the ChromaDB collection."""
    logger.info("=" * 60)
    logger.info("ADDING DOCUMENTS TO KNOWLEDGE BASE")
    logger.info("=" * 60)
    logger.info("Total documents to add: %d", len(ids))
    logger.info("Vector dimension: %d", len(embeddings[0]) if embeddings else 0)
    
    collection = get_collection()
    
    # ChromaDB supports batching up to ~41666 in a single call; chunk if needed
    batch_size = 10
    num_batches = -(-len(ids) // batch_size)
    
    logger.info("Inserting in %d batch(es) of max %d documents each", num_batches, batch_size)
    
    for i in range(0, len(ids), batch_size):
        batch_num = (i // batch_size) + 1
        batch_end = min(i + batch_size, len(ids))
        
        logger.info("  Inserting batch %d/%d (%d documents)...", 
                   batch_num, num_batches, batch_end - i)
        
        collection.add(
            ids=ids[i:batch_end],
            documents=texts[i:batch_end],
            embeddings=embeddings[i:batch_end],
            metadatas=metadatas[i:batch_end],
        )
        
        logger.info("    ✓ Batch %d inserted successfully", batch_num)
    
    final_count = collection.count()
    logger.info("=" * 60)
    logger.info("KNOWLEDGE BASE UPDATED")
    logger.info("Total documents in KB: %d", final_count)
    logger.info("=" * 60)


def query_collection(
    query_embedding: list[float],
    n_results: int = 20,
    where: Optional[dict] = None,
) -> dict:
    """Query the ChromaDB collection with a dense vector. Returns raw Chroma result dict."""
    logger.debug("Querying ChromaDB: n_results=%d, filters=%s", n_results, where)
    
    collection = get_collection()
    actual_n = min(n_results, max(collection.count(), 1))
    
    kwargs: dict = {
        "query_embeddings": [query_embedding],
        "n_results": actual_n,
        "include": ["documents", "metadatas", "distances"],
    }
    if where:
        kwargs["where"] = where
    
    results = collection.query(**kwargs)
    result_count = len(results["documents"][0]) if results.get("documents") else 0
    
    logger.debug("ChromaDB query returned %d results", result_count)
    return results


def batch_query_collection(
    query_embeddings: list[list[float]],
    n_results: int = 20,
    where: Optional[dict] = None,
) -> list[dict]:
    """Query ChromaDB with multiple embeddings in ONE call.

    Returns a list of result dicts (one per query), each in the same
    format as ``query_collection`` (i.e. single-query shaped).
    """
    if not query_embeddings:
        return []

    collection = get_collection()
    actual_n = min(n_results, max(collection.count(), 1))

    logger.debug(
        "Batch querying ChromaDB: %d queries × top-%d",
        len(query_embeddings), actual_n,
    )

    kwargs: dict = {
        "query_embeddings": query_embeddings,
        "n_results": actual_n,
        "include": ["documents", "metadatas", "distances"],
    }
    if where:
        kwargs["where"] = where

    raw = collection.query(**kwargs)

    # Split the multi-query result into per-query dicts
    per_query: list[dict] = []
    num_queries = len(query_embeddings)
    for i in range(num_queries):
        per_query.append({
            "documents": [raw["documents"][i]] if raw.get("documents") else [[]],
            "metadatas": [raw["metadatas"][i]] if raw.get("metadatas") else [[]],
            "distances": [raw["distances"][i]] if raw.get("distances") else [[]],
        })

    total = sum(
        len(r["documents"][0]) for r in per_query
    )
    logger.debug(
        "Batch query returned %d total results across %d queries",
        total, num_queries,
    )
    return per_query


# ---------------------------------------------------------------------------
# Feedback loop: store verified claims back into KB
# ---------------------------------------------------------------------------

def store_verified_claim(
    claim: str,
    verdict: str,
    confidence: float,
    reasoning: str,
    citations: list[dict],
    evidence_chunks: list[dict],
) -> None:
    """Store a verified claim and its supporting evidence into ChromaDB.

    This implements the RAG feedback loop: every verification enriches the KB
    so future queries about the same or similar topics get faster, KB-only answers.
    """
    import hashlib
    import time

    logger.info("-" * 60)
    logger.info("FEEDBACK LOOP: Checking if claim already exists in KB")
    logger.info("-" * 60)

    collection = get_collection()
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Check if this claim verdict already exists in KB
    claim_id = hashlib.sha256(f"verified_claim::{claim}".encode()).hexdigest()[:16]

    try:
        existing = collection.get(ids=[claim_id], include=["metadatas"])
        if existing and existing.get("ids") and len(existing["ids"]) > 0:
            old_meta = existing["metadatas"][0] if existing.get("metadatas") else {}
            if old_meta.get("citation_urls"):
                logger.info("  ✓ Claim already exists in KB with citations (id=%s) – skipping", claim_id)
                logger.info("-" * 60)
                return
            else:
                # Old entry is missing citation_urls – delete and re-store with updated metadata
                logger.info("  ↻ Claim exists but missing citation_urls – updating (id=%s)", claim_id)
                collection.delete(ids=[claim_id])
    except Exception:
        pass  # ID not found, proceed to store

    logger.info("  Claim not found in KB – storing new verified claim")

    texts_to_store: list[str] = []
    ids_to_store: list[str] = []
    metas_to_store: list[dict] = []

    # 1. Store the claim + verdict as a document
    claim_doc = (
        f"Verified Claim: {claim}\n"
        f"Verdict: {verdict}\n"
        f"Confidence: {confidence:.2f}\n"
        f"Reasoning: {reasoning}"
    )

    # Build a JSON string of citation URLs for cache retrieval later
    import json as _json
    citation_urls = _json.dumps([
        {"source_name": c.get("source_name", ""), "url": c.get("url", "")}
        for c in citations if c.get("url")
    ])

    texts_to_store.append(claim_doc)
    ids_to_store.append(claim_id)
    metas_to_store.append({
        "source_name": "Verified Claim (System)",
        "source_url": "",
        "category": "verified_claim",
        "publish_date": timestamp,
        "credibility_score": min(0.95, confidence),
        "verdict": verdict,
        "confidence": confidence,
        "doc_type": "verified_claim",
        "citation_urls": citation_urls,  # JSON array of {source_name, url}
        "reasoning": reasoning[:500],    # truncated for metadata size limits
    })

    # 2. Store web evidence chunks that aren't already in KB
    for i, chunk in enumerate(evidence_chunks):
        chunk_text = chunk.get("text", "")
        if not chunk_text or len(chunk_text) < 50:
            continue
        # Only store web evidence (KB evidence is already there)
        if chunk.get("retrieval_method") != "web_search":
            continue

        chunk_id = hashlib.sha256(
            f"web_evidence::{claim[:100]}::{i}".encode()
        ).hexdigest()[:16]

        # Check if this evidence chunk already exists
        try:
            existing_chunk = collection.get(ids=[chunk_id], include=["metadatas"])
            if existing_chunk and existing_chunk.get("ids") and len(existing_chunk["ids"]) > 0:
                continue  # Already in KB, skip
        except Exception:
            pass

        texts_to_store.append(chunk_text)
        ids_to_store.append(chunk_id)
        metas_to_store.append({
            "source_name": chunk.get("source_name", "Web"),
            "source_url": chunk.get("source_url", ""),
            "category": "web_evidence",
            "publish_date": chunk.get("publish_date", timestamp),
            "credibility_score": chunk.get("credibility_score", 0.5),
            "doc_type": "web_evidence",
            "related_claim": claim[:200],
        })

    if not texts_to_store:
        logger.info("  No new documents to store (all data already in KB)")
        logger.info("-" * 60)
        return

    logger.info("  Storing %d new documents: %d claim(s) + %d web evidence chunks",
                len(texts_to_store),
                sum(1 for m in metas_to_store if m.get("doc_type") == "verified_claim"),
                sum(1 for m in metas_to_store if m.get("doc_type") == "web_evidence"))

    # Embed and store
    embeddings = embed_texts(texts_to_store)
    collection.add(
        ids=ids_to_store,
        documents=texts_to_store,
        embeddings=embeddings,
        metadatas=metas_to_store,
    )

    logger.info("  ✓ Feedback loop complete: KB now has %d documents", collection.count())
    logger.info("-" * 60)


def _parse_cached_meta(meta: dict, similarity: float) -> dict:
    """Parse ChromaDB metadata into a cache-hit dict."""
    import json as _json
    raw_urls = meta.get("citation_urls", "[]")
    try:
        citation_urls = _json.loads(raw_urls) if raw_urls else []
    except (ValueError, TypeError):
        citation_urls = []
    return {
        "verdict": meta.get("verdict", "NOT_ENOUGH_EVIDENCE"),
        "confidence": float(meta.get("confidence", 0.0)),
        "reasoning": meta.get("reasoning", ""),
        "citation_urls": citation_urls,
        "similarity": similarity,
    }


def lookup_cached_verdict_by_id(claim: str) -> Optional[dict]:
    """Fast O(1) lookup by deterministic hash ID — no embedding needed.

    Returns a cache-hit dict or None.
    """
    import hashlib
    collection = get_collection()
    claim_id = hashlib.sha256(f"verified_claim::{claim}".encode()).hexdigest()[:16]

    try:
        existing = collection.get(ids=[claim_id], include=["metadatas"])
        if existing and existing.get("ids") and len(existing["ids"]) > 0:
            meta = existing["metadatas"][0]
            if meta.get("doc_type") == "verified_claim":
                logger.info("  ✓ Cache HIT (exact ID match): verdict=%s", meta.get("verdict", "?"))
                return _parse_cached_meta(meta, similarity=1.0)
    except Exception:
        pass
    return None


def lookup_cached_verdict_by_embedding(
    claim_embedding: list[float],
    similarity_threshold: float = 0.92,
) -> Optional[dict]:
    """Embedding-based similarity lookup — slower, catches paraphrased claims.

    Returns a cache-hit dict or None.
    """
    collection = get_collection()
    if collection.count() == 0:
        return None

    results = collection.query(
        query_embeddings=[claim_embedding],
        n_results=3,
        where={"doc_type": "verified_claim"},
        include=["documents", "metadatas", "distances"],
    )

    if not results or not results.get("documents") or not results["documents"][0]:
        return None

    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        similarity = 1.0 - dist  # cosine distance → similarity
        if similarity < similarity_threshold:
            continue

        logger.info(
            "  ✓ Cache HIT (embedding): similarity=%.3f, verdict=%s",
            similarity, meta.get("verdict", "?"),
        )
        return _parse_cached_meta(meta, similarity)

    logger.debug("  Cache MISS: no verified claim matched above %.2f threshold", similarity_threshold)
    return None
