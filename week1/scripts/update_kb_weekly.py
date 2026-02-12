#!/usr/bin/env python3
"""Weekly knowledge base update script.

Runs:
  1. Wikipedia article updates (top 50 political/current event topics)
  2. Health check

Usage:
    python scripts/update_kb_weekly.py

Setup as cron job (runs weekly on Sunday at 3 AM):
    0 3 * * 0 cd /path/to/week1 && python scripts/update_kb_weekly.py >> logs/weekly_update.log 2>&1
"""

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_path))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


async def main():
    """Run weekly update process."""
    logger.info("\n" + "=" * 80)
    logger.info("STARTING WEEKLY UPDATE: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    logger.info("=" * 80)

    try:
        # Import here to ensure config is loaded
        from app.services.data_updater import run_weekly_update

        # Run weekly update
        stats = await run_weekly_update()

        # Log results
        logger.info("\n" + "=" * 80)
        logger.info("WEEKLY UPDATE SUMMARY")
        logger.info("=" * 80)
        logger.info("Timestamp: %s", stats.get("timestamp", "unknown"))
        logger.info("Wikipedia articles fetched: %d", stats.get("wikipedia_articles_fetched", 0))
        logger.info("Chunks ingested: %d", stats.get("wikipedia_articles_ingested", 0))

        if "error" in stats:
            logger.error("Error occurred: %s", stats["error"])
            logger.info("=" * 80 + "\n")
            return 1

        logger.info("Status: ✓ SUCCESS")
        logger.info("=" * 80 + "\n")

        # Run health check
        logger.info("Running post-update health check...")
        from monitor_kb_health import check_kb_health
        health_stats = check_kb_health()

        if health_stats.get("status") == "alerts":
            logger.warning("Health check found issues - see above")
            return 1

        return 0

    except Exception as exc:
        logger.error("Weekly update failed: %s", exc, exc_info=True)
        return 2


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
