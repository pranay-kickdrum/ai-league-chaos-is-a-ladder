"""Data update service for keeping the knowledge base fresh.

Phase 2 implementation:
  - RSS feed polling for news articles
  - Wikipedia article updates
  - TTL-based cleanup
  - Source freshness tracking
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional

import feedparser
import httpx
import wikipediaapi

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# RSS Feed Polling
# ---------------------------------------------------------------------------

async def fetch_rss_feeds(feeds: list[str] | None = None) -> list[dict]:
    """Fetch articles from RSS feeds and return as documents ready for ingestion.

    Args:
        feeds: List of RSS feed URLs. Defaults to settings.rss_feeds.

    Returns:
        List of document dicts with text and metadata.
    """
    if feeds is None:
        feeds = settings.rss_feeds

    logger.info("Fetching RSS feeds: %d sources", len(feeds))

    all_docs: list[dict] = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        for feed_url in feeds:
            try:
                logger.info("  Polling: %s", feed_url)

                # Fetch feed
                response = await client.get(feed_url)
                response.raise_for_status()

                # Parse with feedparser
                feed = feedparser.parse(response.text)

                # Extract articles
                for entry in feed.entries:
                    # Get article content
                    title = entry.get("title", "")
                    summary = entry.get("summary", entry.get("description", ""))
                    link = entry.get("link", "")

                    # Parse publish date
                    publish_date = "unknown"
                    if hasattr(entry, "published_parsed") and entry.published_parsed:
                        dt = datetime(*entry.published_parsed[:6])
                        publish_date = dt.isoformat()
                    elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                        dt = datetime(*entry.updated_parsed[:6])
                        publish_date = dt.isoformat()

                    # Build text
                    text = f"# {title}\n\n{summary}"

                    # Determine source name from feed
                    source_name = feed.feed.get("title", "News")

                    # Calculate credibility based on source
                    credibility_score = _score_news_source(link)

                    # Calculate expiration (30 days from now)
                    expires_at = (datetime.now() + timedelta(days=settings.ttl_news_articles)).isoformat()

                    all_docs.append({
                        "text": text,
                        "metadata": {
                            "source_name": source_name,
                            "source_url": link,
                            "category": "news",
                            "publish_date": publish_date,
                            "credibility_score": credibility_score,
                            "ingested_at": datetime.now().isoformat(),
                            "expires_at": expires_at,
                            "last_verified": datetime.now().isoformat(),
                            "source_type": "rss_feed",
                            "is_historical": False,
                        },
                    })

                logger.info("    ✓ Fetched %d articles", len(feed.entries))

            except Exception as exc:
                logger.error("    ✗ Failed to fetch %s: %s", feed_url, exc)
                continue

    logger.info("✓ Total articles fetched from RSS: %d", len(all_docs))
    return all_docs


def _score_news_source(url: str) -> float:
    """Score news source credibility based on domain."""
    CREDIBILITY_MAP = {
        # Tier 1: 0.95
        "reuters.com": 0.95,
        "ap.org": 0.95,
        "apnews.com": 0.95,
        "bbc.com": 0.95,
        "bbc.co.uk": 0.95,
        "nytimes.com": 0.95,
        "washingtonpost.com": 0.95,
        "wsj.com": 0.95,

        # Tier 2: 0.85
        "cnn.com": 0.85,
        "theguardian.com": 0.85,
        "npr.org": 0.85,
        "bloomberg.com": 0.85,
        "ft.com": 0.85,
        "economist.com": 0.85,
        "usatoday.com": 0.85,

        # Tier 3: 0.75
        "nbcnews.com": 0.75,
        "cbsnews.com": 0.75,
        "abcnews.go.com": 0.75,
        "politico.com": 0.75,
        "thehill.com": 0.75,

        # Government/Edu: 0.90
        ".gov": 0.90,
        ".edu": 0.90,
    }

    url_lower = url.lower()

    # Check exact domain matches
    for domain, score in CREDIBILITY_MAP.items():
        if domain in url_lower:
            return score

    # Default for unknown sources
    return 0.60


# ---------------------------------------------------------------------------
# Wikipedia Updates
# ---------------------------------------------------------------------------

async def fetch_wikipedia_articles(topics: list[str] | None = None) -> list[dict]:
    """Fetch Wikipedia articles for specified topics.

    Args:
        topics: List of Wikipedia page titles. Defaults to settings.wikipedia_topics.

    Returns:
        List of document dicts with text and metadata.
    """
    if topics is None:
        topics = settings.wikipedia_topics

    logger.info("Fetching Wikipedia articles: %d topics", len(topics))

    # Initialize Wikipedia API client
    wiki = wikipediaapi.Wikipedia(
        user_agent="ClaimVerificationBot/1.0 (Educational Project)",
        language="en",
    )

    all_docs: list[dict] = []

    for topic in topics:
        try:
            logger.info("  Fetching: %s", topic)

            page = wiki.page(topic)

            if not page.exists():
                logger.warning("    ⚠ Page does not exist: %s", topic)
                continue

            # Get full text
            text = page.text
            if not text or len(text) < 100:
                logger.warning("    ⚠ Page too short: %s", topic)
                continue

            # Get summary (first paragraph)
            summary = page.summary

            # Build rich text
            full_text = f"# {page.title}\n\n{text}"

            # Calculate expiration (90 days from now)
            expires_at = (datetime.now() + timedelta(days=settings.ttl_wikipedia)).isoformat()

            all_docs.append({
                "text": full_text,
                "metadata": {
                    "source_name": "Wikipedia",
                    "source_url": page.fullurl,
                    "category": "wiki",
                    "publish_date": "unknown",  # Wikipedia doesn't expose last modified via API easily
                    "credibility_score": 0.90,
                    "ingested_at": datetime.now().isoformat(),
                    "expires_at": expires_at,
                    "last_verified": datetime.now().isoformat(),
                    "source_type": "wikipedia",
                    "is_historical": False,
                    "page_title": page.title,
                },
            })

            logger.info("    ✓ Fetched (length: %d chars)", len(text))

        except Exception as exc:
            logger.error("    ✗ Failed to fetch %s: %s", topic, exc)
            continue

    logger.info("✓ Total Wikipedia articles fetched: %d", len(all_docs))
    return all_docs


# ---------------------------------------------------------------------------
# TTL-Based Cleanup
# ---------------------------------------------------------------------------

def cleanup_expired_documents() -> int:
    """Remove expired documents from ChromaDB based on expires_at metadata.

    Returns:
        Number of documents deleted.
    """
    logger.info("Starting TTL-based cleanup...")

    try:
        # Lazy import to avoid circular dependency
        from app.services.embedder import get_collection

        collection = get_collection()

        # Get all documents
        results = collection.get(include=["metadatas"])

        if not results or not results["ids"]:
            logger.info("  No documents in collection")
            return 0

        # Find expired documents
        expired_ids = []
        now = datetime.now()

        for doc_id, metadata in zip(results["ids"], results["metadatas"]):
            expires_at = metadata.get("expires_at")

            if expires_at and expires_at != "never":
                try:
                    expiry_date = datetime.fromisoformat(expires_at)
                    if expiry_date < now:
                        expired_ids.append(doc_id)
                except Exception:
                    continue

        if not expired_ids:
            logger.info("  ✓ No expired documents found")
            return 0

        # Delete expired documents
        logger.info("  Deleting %d expired documents...", len(expired_ids))
        collection.delete(ids=expired_ids)

        logger.info("✓ Cleanup complete: %d documents removed", len(expired_ids))
        return len(expired_ids)

    except Exception as exc:
        logger.error("✗ Cleanup failed: %s", exc)
        return 0


# ---------------------------------------------------------------------------
# Differential Update (avoid re-embedding unchanged content)
# ---------------------------------------------------------------------------

def get_existing_document_hash(source_url: str) -> Optional[str]:
    """Get the content hash of an existing document by source URL.

    Args:
        source_url: The source URL of the document.

    Returns:
        The content hash if found, None otherwise.
    """
    try:
        from app.services.embedder import get_collection

        collection = get_collection()

        # Query by metadata
        results = collection.get(
            where={"source_url": source_url},
            include=["metadatas"],
            limit=1,
        )

        if results and results["metadatas"]:
            return results["metadatas"][0].get("content_hash")

        return None

    except Exception as exc:
        logger.error("Failed to get document hash: %s", exc)
        return None


def compute_content_hash(text: str) -> str:
    """Compute SHA-256 hash of content."""
    return hashlib.sha256(text.encode()).hexdigest()


async def smart_update_document(url: str, new_text: str, metadata: dict) -> bool:
    """Update document only if content has changed.

    Args:
        url: Source URL
        new_text: New content
        metadata: Document metadata

    Returns:
        True if document was updated, False if unchanged.
    """
    new_hash = compute_content_hash(new_text)
    old_hash = get_existing_document_hash(url)

    if old_hash == new_hash:
        # Content unchanged - just update last_verified timestamp
        logger.info("  Content unchanged for %s, updating timestamp only", url)
        _update_metadata_only(url, {"last_verified": datetime.now().isoformat()})
        return False

    # Content changed - re-embed
    logger.info("  Content changed for %s, re-embedding...", url)
    metadata["content_hash"] = new_hash

    # Delete old version and insert new
    await _reindex_document(url, new_text, metadata)
    return True


def _update_metadata_only(source_url: str, updates: dict) -> None:
    """Update only metadata for a document (no re-embedding)."""
    try:
        from app.services.embedder import get_collection

        collection = get_collection()

        # Get document IDs for this source
        results = collection.get(
            where={"source_url": source_url},
            include=["metadatas"],
        )

        if not results or not results["ids"]:
            return

        # Update metadata for all chunks from this source
        for doc_id, old_meta in zip(results["ids"], results["metadatas"]):
            new_meta = {**old_meta, **updates}
            collection.update(ids=[doc_id], metadatas=[new_meta])

    except Exception as exc:
        logger.error("Failed to update metadata: %s", exc)


async def _reindex_document(source_url: str, text: str, metadata: dict) -> None:
    """Delete old document and re-index with new content."""
    try:
        from app.services.embedder import get_collection
        from app.knowledge_base.ingest import chunk_text
        from app.services.embedder import embed_texts, add_documents

        collection = get_collection()

        # Delete old version
        results = collection.get(where={"source_url": source_url})
        if results and results["ids"]:
            collection.delete(ids=results["ids"])
            logger.info("    Deleted %d old chunks", len(results["ids"]))

        # Chunk new content
        chunks = chunk_text(text)

        # Generate new IDs
        from app.knowledge_base.ingest import _doc_id
        doc_ids = [_doc_id(source_url, i) for i in range(len(chunks))]

        # Add chunk metadata
        metadatas = [{**metadata, "chunk_index": i} for i in range(len(chunks))]

        # Embed and store
        embeddings = embed_texts(chunks)
        add_documents(doc_ids, chunks, embeddings, metadatas)

        logger.info("    ✓ Re-indexed with %d new chunks", len(chunks))

    except Exception as exc:
        logger.error("Failed to reindex document: %s", exc)


# ---------------------------------------------------------------------------
# Main Update Orchestrator
# ---------------------------------------------------------------------------

async def run_daily_update() -> dict:
    """Run daily update: fetch RSS feeds and cleanup expired docs.

    Returns:
        Statistics dict with counts.
    """
    logger.info("\n" + "=" * 80)
    logger.info("DAILY UPDATE - RSS FEEDS & CLEANUP")
    logger.info("=" * 80)

    stats = {
        "rss_articles_fetched": 0,
        "rss_articles_ingested": 0,
        "expired_deleted": 0,
        "timestamp": datetime.now().isoformat(),
    }

    try:
        # Step 1: Fetch RSS feeds
        rss_docs = await fetch_rss_feeds()
        stats["rss_articles_fetched"] = len(rss_docs)

        # Step 2: Ingest new articles
        if rss_docs:
            from app.knowledge_base.ingest import ingest_documents
            chunks_added = ingest_documents(rss_docs, source_label="rss_daily_update")
            stats["rss_articles_ingested"] = chunks_added

        # Step 3: Cleanup expired documents
        deleted_count = cleanup_expired_documents()
        stats["expired_deleted"] = deleted_count

        logger.info("\n" + "=" * 80)
        logger.info("DAILY UPDATE COMPLETE")
        logger.info("  RSS articles fetched: %d", stats["rss_articles_fetched"])
        logger.info("  Chunks ingested: %d", stats["rss_articles_ingested"])
        logger.info("  Expired documents deleted: %d", stats["expired_deleted"])
        logger.info("=" * 80 + "\n")

    except Exception as exc:
        logger.error("Daily update failed: %s", exc)
        stats["error"] = str(exc)

    return stats


async def run_weekly_update() -> dict:
    """Run weekly update: fetch Wikipedia articles.

    Returns:
        Statistics dict with counts.
    """
    logger.info("\n" + "=" * 80)
    logger.info("WEEKLY UPDATE - WIKIPEDIA ARTICLES")
    logger.info("=" * 80)

    stats = {
        "wikipedia_articles_fetched": 0,
        "wikipedia_articles_ingested": 0,
        "timestamp": datetime.now().isoformat(),
    }

    try:
        # Fetch Wikipedia articles
        wiki_docs = await fetch_wikipedia_articles()
        stats["wikipedia_articles_fetched"] = len(wiki_docs)

        # Ingest articles
        if wiki_docs:
            from app.knowledge_base.ingest import ingest_documents
            chunks_added = ingest_documents(wiki_docs, source_label="wikipedia_weekly_update")
            stats["wikipedia_articles_ingested"] = chunks_added

        logger.info("\n" + "=" * 80)
        logger.info("WEEKLY UPDATE COMPLETE")
        logger.info("  Wikipedia articles fetched: %d", stats["wikipedia_articles_fetched"])
        logger.info("  Chunks ingested: %d", stats["wikipedia_articles_ingested"])
        logger.info("=" * 80 + "\n")

    except Exception as exc:
        logger.error("Weekly update failed: %s", exc)
        stats["error"] = str(exc)

    return stats
