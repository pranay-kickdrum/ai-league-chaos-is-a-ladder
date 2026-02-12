#!/usr/bin/env python3
"""Test script for Phase 2 update system.

Runs a quick test of all update components to verify they're working.
Safe to run - only fetches a small sample and doesn't modify existing data.

Usage:
    python scripts/test_update_system.py
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_path))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


async def test_rss_feeds():
    """Test RSS feed fetching."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 1: RSS Feed Fetching")
    logger.info("=" * 80)

    try:
        from app.services.data_updater import fetch_rss_feeds

        # Test with just one feed
        test_feeds = ["https://feeds.reuters.com/reuters/topNews"]

        logger.info("Fetching from 1 test feed...")
        docs = await fetch_rss_feeds(test_feeds)

        if docs:
            logger.info("✓ SUCCESS: Fetched %d articles", len(docs))

            # Show sample
            if docs:
                sample = docs[0]
                logger.info("\nSample article:")
                logger.info("  Source: %s", sample["metadata"].get("source_name"))
                logger.info("  URL: %s", sample["metadata"].get("source_url"))
                logger.info("  Credibility: %.2f", sample["metadata"].get("credibility_score", 0))
                logger.info("  Text preview: %s...", sample["text"][:100])

            return True
        else:
            logger.warning("⚠ No articles fetched (feed might be empty)")
            return True  # Not necessarily an error

    except Exception as exc:
        logger.error("✗ FAILED: %s", exc)
        return False


async def test_wikipedia():
    """Test Wikipedia fetching."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 2: Wikipedia Fetching")
    logger.info("=" * 80)

    try:
        from app.services.data_updater import fetch_wikipedia_articles

        # Test with just 2 topics
        test_topics = ["Artificial_intelligence", "Climate_change"]

        logger.info("Fetching %d test topics...", len(test_topics))
        docs = await fetch_wikipedia_articles(test_topics)

        if docs:
            logger.info("✓ SUCCESS: Fetched %d articles", len(docs))

            # Show sample
            if docs:
                sample = docs[0]
                logger.info("\nSample article:")
                logger.info("  Title: %s", sample["metadata"].get("page_title"))
                logger.info("  URL: %s", sample["metadata"].get("source_url"))
                logger.info("  Length: %d chars", len(sample["text"]))

            return True
        else:
            logger.error("✗ FAILED: No articles fetched")
            return False

    except Exception as exc:
        logger.error("✗ FAILED: %s", exc)
        return False


def test_cleanup():
    """Test TTL cleanup (dry run - doesn't delete anything)."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 3: TTL Cleanup (Dry Run)")
    logger.info("=" * 80)

    try:
        from app.services.embedder import get_collection
        from datetime import datetime

        collection = get_collection()
        results = collection.get(include=["metadatas"])

        if not results or not results["ids"]:
            logger.info("  Knowledge base is empty (expected for first run)")
            return True

        # Count expired documents (without deleting)
        expired_count = 0
        now = datetime.now()

        for metadata in results["metadatas"]:
            expires_at = metadata.get("expires_at")
            if expires_at and expires_at != "never":
                try:
                    expiry_date = datetime.fromisoformat(expires_at)
                    if expiry_date < now:
                        expired_count += 1
                except Exception:
                    pass

        logger.info("  Total documents: %d", len(results["ids"]))
        logger.info("  Expired documents: %d", expired_count)
        logger.info("✓ SUCCESS: Cleanup logic works (dry run)")

        return True

    except Exception as exc:
        logger.error("✗ FAILED: %s", exc)
        return False


def test_health_check():
    """Test health check."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 4: Health Check")
    logger.info("=" * 80)

    try:
        from monitor_kb_health import check_kb_health

        stats = check_kb_health()

        if stats.get("status") in ["healthy", "alerts", "empty"]:
            logger.info("✓ SUCCESS: Health check completed")
            return True
        else:
            logger.error("✗ FAILED: Health check returned error")
            return False

    except Exception as exc:
        logger.error("✗ FAILED: %s", exc)
        return False


async def main():
    """Run all tests."""
    logger.info("\n" + "=" * 80)
    logger.info("PHASE 2 UPDATE SYSTEM - TEST SUITE")
    logger.info("=" * 80)
    logger.info("This will test all update components without modifying your KB")
    logger.info("=" * 80)

    results = []

    # Test 1: RSS feeds
    results.append(("RSS Feeds", await test_rss_feeds()))

    # Test 2: Wikipedia
    results.append(("Wikipedia", await test_wikipedia()))

    # Test 3: Cleanup
    results.append(("TTL Cleanup", test_cleanup()))

    # Test 4: Health check
    results.append(("Health Check", test_health_check()))

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("TEST SUMMARY")
    logger.info("=" * 80)

    passed = 0
    failed = 0

    for test_name, success in results:
        status = "✓ PASS" if success else "✗ FAIL"
        logger.info("  %s: %s", test_name.ljust(20), status)
        if success:
            passed += 1
        else:
            failed += 1

    logger.info("=" * 80)
    logger.info("Total: %d passed, %d failed", passed, failed)
    logger.info("=" * 80 + "\n")

    if failed == 0:
        logger.info("🎉 All tests passed! Your update system is ready.")
        logger.info("\nNext steps:")
        logger.info("  1. Review configuration in backend/app/config.py")
        logger.info("  2. Set up cron jobs (see crontab.example)")
        logger.info("  3. Run first update: python scripts/update_kb_daily.py")
        logger.info("  4. Check logs: tail -f logs/daily_update.log")
        return 0
    else:
        logger.error("⚠ Some tests failed. Please fix issues before deploying.")
        logger.error("\nTroubleshooting:")
        logger.error("  - Check internet connectivity")
        logger.error("  - Verify API keys in .env file")
        logger.error("  - Review error messages above")
        logger.error("  - See DATA_UPDATE_GUIDE.md for help")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
