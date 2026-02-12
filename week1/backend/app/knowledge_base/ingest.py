"""Knowledge-base ingestion: chunk, embed, and store documents in ChromaDB.

Supports:
  - LIAR dataset (TSV)
  - Plain-text / JSON article files
  - Wikipedia API downloads
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import textwrap
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Text chunking
# ---------------------------------------------------------------------------

def chunk_text(
    text: str,
    chunk_size: int = 2000,
    overlap: int = 250,
) -> list[str]:
    """Split *text* into overlapping chunks (by character count).

    Uses paragraph boundaries when possible, falling back to sentence
    then character splitting.
    """
    if len(text) <= chunk_size:
        return [text.strip()] if text.strip() else []

    chunks: list[str] = []
    start = 0
    max_iterations = len(text) // (chunk_size - overlap) + 10  # Safety limit
    iteration = 0
    
    while start < len(text) and iteration < max_iterations:
        iteration += 1
        end = start + chunk_size

        # Try to break at a paragraph boundary
        segment = text[start:end]
        break_pos = segment.rfind("\n\n")
        if break_pos == -1 or break_pos < chunk_size // 3:
            # fall back to sentence boundary
            break_pos = segment.rfind(". ")
        if break_pos == -1 or break_pos < chunk_size // 3:
            break_pos = len(segment)
        else:
            break_pos += 1  # include the delimiter

        chunk = text[start : start + break_pos].strip()
        if chunk:
            chunks.append(chunk)

        # Ensure we always make forward progress
        next_start = start + max(break_pos - overlap, 1)
        if next_start <= start:
            # Force advance if we're stuck
            next_start = start + chunk_size
        start = next_start

    if iteration >= max_iterations:
        logger.warning("chunk_text hit iteration limit (%d) - text may be incompletely chunked", max_iterations)
    
    return chunks


def _doc_id(source: str, index: int) -> str:
    """Deterministic document ID."""
    raw = f"{source}::{index}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# LIAR dataset loader
# ---------------------------------------------------------------------------

def load_liar_dataset(tsv_path: str | Path) -> list[dict]:
    """Parse the LIAR TSV file and return list of dicts ready for ingestion.

    LIAR columns (tab-separated, no header):
      0: id, 1: label, 2: statement, 3: subject(s), 4: speaker,
      5: speaker_job, 6: state_info, 7: party, 8-12: credit counts, 13: context
    """
    tsv_path = Path(tsv_path)
    if not tsv_path.exists():
        logger.warning("LIAR file not found: %s", tsv_path)
        return []

    logger.info("Loading LIAR dataset: %s", tsv_path.name)
    
    docs: list[dict] = []
    with open(tsv_path, encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t")
        for row_num, row in enumerate(reader, 1):
            if len(row) < 3:
                continue
            label = row[1].strip().lower()
            statement = row[2].strip()
            speaker = row[4].strip() if len(row) > 4 else "unknown"
            context = row[13].strip() if len(row) > 13 else ""

            # Build a rich text block
            text = f"Claim: {statement}"
            if speaker:
                text += f"\nSpeaker: {speaker}"
            if context:
                text += f"\nContext: {context}"
            text += f"\nVerdict: {label}"

            docs.append({
                "text": text,
                "metadata": {
                    "source_name": "LIAR / PolitiFact",
                    "source_url": "https://www.politifact.com/",
                    "category": "fact_check",
                    "publish_date": "unknown",
                    "credibility_score": 0.85,
                    "label": label,
                    "ingested_at": "unknown",  # Initial ingestion - set during ingest_documents
                    "expires_at": "never",  # Fact-checks never expire
                    "is_historical": True,  # LIAR dataset is historical
                },
            })
    
    logger.info("✓ Loaded %d statements from LIAR dataset", len(docs))
    
    # Show label distribution
    if docs:
        labels = {}
        for d in docs:
            label = d["metadata"].get("label", "unknown")
            labels[label] = labels.get(label, 0) + 1
        logger.info("  Label distribution: %s", labels)
    
    return docs


# ---------------------------------------------------------------------------
# Wikipedia article loader (from pre-downloaded JSON files)
# ---------------------------------------------------------------------------

def load_wiki_articles(directory: str | Path) -> list[dict]:
    """Load Wikipedia articles stored as JSON files (title + text)."""
    directory = Path(directory)
    if not directory.exists():
        logger.warning("Wiki directory not found: %s", directory)
        return []

    logger.info("Loading Wikipedia articles from: %s", directory)
    
    docs: list[dict] = []
    for fp in directory.glob("*.json"):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            title = data.get("title", fp.stem)
            text = data.get("text", data.get("extract", ""))
            if not text:
                continue
            docs.append({
                "text": f"# {title}\n\n{text}",
                "metadata": {
                    "source_name": "Wikipedia",
                    "source_url": f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                    "category": "wiki",
                    "publish_date": "unknown",
                    "credibility_score": 0.90,
                    "ingested_at": "unknown",  # Set during ingest_documents
                    "expires_at": "unknown",  # Set during ingest_documents (90 days)
                    "is_historical": False,
                },
            })
        except Exception as exc:
            logger.warning("Failed to load %s: %s", fp, exc)

    logger.info("✓ Loaded %d Wikipedia articles", len(docs))
    return docs


# ---------------------------------------------------------------------------
# Main ingestion pipeline
# ---------------------------------------------------------------------------

def ingest_documents(
    docs: list[dict],
    source_label: str = "generic",
    batch_size: int = 1000,
) -> int:
    """Chunk, embed, and insert *docs* into ChromaDB in batches.

    Each item in *docs* should have keys: ``text``, ``metadata`` (dict).
    Processes documents in batches to avoid memory issues with large datasets.
    Returns number of chunks inserted.
    """
    logger.info("\n" + "=" * 80)
    logger.info("KNOWLEDGE BASE INGESTION: %s", source_label)
    logger.info("=" * 80)
    
    if not docs:
        logger.warning("⚠ No documents to ingest")
        return 0

    # Lazy imports to avoid circular dependency and allow CLI usage
    from app.services.embedder import embed_texts, add_documents
    from app.config import settings

    logger.info("Total documents: %d", len(docs))
    logger.info("Processing in batches of %d documents", batch_size)
    logger.info("Chunk size: 512 tokens (~2000 chars), Overlap: 64 tokens (~250 chars)")
    logger.info("=" * 80)
    
    total_chunks = 0
    num_batches = -(-len(docs) // batch_size)  # ceiling division
    
    for batch_idx in range(0, len(docs), batch_size):
        batch_num = (batch_idx // batch_size) + 1
        batch_docs = docs[batch_idx : batch_idx + batch_size]
        
        logger.info("\n[BATCH %d/%d] Processing %d documents...", 
                   batch_num, num_batches, len(batch_docs))
        logger.info("-" * 80)
        
        # STEP 1: Chunk documents in this batch
        logger.info("[Step 1/3] Chunking documents...")
        all_ids: list[str] = []
        all_texts: list[str] = []
        all_metas: list[dict] = []

        for doc_idx_in_batch, doc in enumerate(batch_docs):
            global_doc_idx = batch_idx + doc_idx_in_batch
            
            try:
                # Log progress every 10 documents
                if doc_idx_in_batch % 10 == 0:
                    logger.debug("    Chunking document %d/%d in batch...", doc_idx_in_batch + 1, len(batch_docs))
                
                doc_text = doc.get("text", "")
                if not doc_text or len(doc_text.strip()) == 0:
                    logger.warning("    Skipping empty document at index %d", global_doc_idx)
                    continue
                
                # Truncate extremely large documents (> 50k chars)
                if len(doc_text) > 50000:
                    logger.warning("    Truncating large document at index %d (length: %d)", global_doc_idx, len(doc_text))
                    doc_text = doc_text[:50000]
                
                chunks = chunk_text(doc_text)

                for ci, chunk in enumerate(chunks):
                    doc_id = _doc_id(f"{source_label}:{global_doc_idx}", ci)
                    meta = {**doc.get("metadata", {}), "chunk_index": ci}

                    # Add/update timestamps if not already set
                    if meta.get("ingested_at") == "unknown" or not meta.get("ingested_at"):
                        meta["ingested_at"] = datetime.now().isoformat()

                    # Set expiration based on category if not already set
                    if meta.get("expires_at") == "unknown" or not meta.get("expires_at"):
                        category = meta.get("category", "unknown")
                        if category == "fact_check":
                            meta["expires_at"] = "never"
                        elif category == "wiki":
                            meta["expires_at"] = (datetime.now() + timedelta(days=settings.ttl_wikipedia)).isoformat()
                        elif category == "news":
                            meta["expires_at"] = (datetime.now() + timedelta(days=settings.ttl_news_articles)).isoformat()
                        else:
                            meta["expires_at"] = (datetime.now() + timedelta(days=180)).isoformat()

                    all_ids.append(doc_id)
                    all_texts.append(chunk)
                    all_metas.append(meta)
            
            except Exception as exc:
                logger.error("    ✗ Failed to chunk document %d: %s", global_doc_idx, exc)
                logger.error("    Document text preview: %s", str(doc.get("text", ""))[:200])
                continue

        if not all_texts:
            logger.warning("  No chunks generated from this batch, skipping")
            continue

        logger.info("  ✓ Generated %d chunks from %d documents", len(all_texts), len(batch_docs))
        
        # Show stats for first batch only
        if batch_num == 1:
            chunk_lengths = [len(c) for c in all_texts]
            avg_length = sum(chunk_lengths) / len(chunk_lengths)
            logger.info("  Average chunk size: %.0f characters", avg_length)
            logger.info("  Min/Max: %d / %d characters", min(chunk_lengths), max(chunk_lengths))

        # STEP 2: Generate embeddings
        logger.info("[Step 2/3] Generating embeddings for %d chunks...", len(all_texts))
        embeddings = embed_texts(all_texts)

        # STEP 3: Store in ChromaDB
        logger.info("[Step 3/3] Storing in knowledge base...")
        add_documents(all_ids, all_texts, embeddings, all_metas)
        
        total_chunks += len(all_texts)
        logger.info("✓ Batch %d/%d complete: %d chunks stored (total so far: %d)",
                   batch_num, num_batches, len(all_texts), total_chunks)

    logger.info("\n" + "=" * 80)
    logger.info("INGESTION COMPLETE: %s", source_label)
    logger.info("Total chunks ingested: %d from %d documents", total_chunks, len(docs))
    logger.info("=" * 80 + "\n")
    
    return total_chunks
