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


def embed_texts(texts: list[str], batch_size: int = 100) -> list[list[float]]:
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
    batch_size = 500
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
