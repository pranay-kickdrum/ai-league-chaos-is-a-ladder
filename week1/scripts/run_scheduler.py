#!/usr/bin/env python3
"""Unified scheduler for knowledge base updates.

Alternative to cron - runs as a long-lived process that schedules updates.
Useful for development or systems where cron is not available.

Usage:
    python scripts/run_scheduler.py

For production, consider using cron instead (see crontab.example).
"""

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

import schedule
import time

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


def run_daily_job():
    """Wrapper for daily update."""
    logger.info("Triggering daily update job...")
    try:
        from app.services.data_updater import run_daily_update
        stats = asyncio.run(run_daily_update())
        logger.info("Daily update completed: %s", stats)
    except Exception as exc:
        logger.error("Daily update failed: %s", exc)


def run_weekly_job():
    """Wrapper for weekly update."""
    logger.info("Triggering weekly update job...")
    try:
        from app.services.data_updater import run_weekly_update
        stats = asyncio.run(run_weekly_update())
        logger.info("Weekly update completed: %s", stats)
    except Exception as exc:
        logger.error("Weekly update failed: %s", exc)


def run_health_check():
    """Wrapper for health check."""
    logger.info("Triggering health check...")
    try:
        from monitor_kb_health import check_kb_health
        stats = check_kb_health()
        logger.info("Health check completed: status=%s", stats.get("status"))
    except Exception as exc:
        logger.error("Health check failed: %s", exc)


def main():
    """Run scheduler loop."""
    logger.info("\n" + "=" * 80)
    logger.info("KNOWLEDGE BASE UPDATE SCHEDULER")
    logger.info("=" * 80)
    logger.info("Starting at: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    logger.info("")
    logger.info("Schedule:")
    logger.info("  - Daily update (RSS + cleanup): Every day at 02:00")
    logger.info("  - Weekly update (Wikipedia): Every Sunday at 03:00")
    logger.info("  - Health check: Every day at 12:00")
    logger.info("")
    logger.info("Press Ctrl+C to stop")
    logger.info("=" * 80 + "\n")

    # Schedule jobs
    schedule.every().day.at("02:00").do(run_daily_job)
    schedule.every().sunday.at("03:00").do(run_weekly_job)
    schedule.every().day.at("12:00").do(run_health_check)

    # For testing: run immediately on startup
    # Uncomment these lines to test the scheduler
    # logger.info("Running initial health check...")
    # run_health_check()

    # Main loop
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
    except KeyboardInterrupt:
        logger.info("\n\nScheduler stopped by user")
        sys.exit(0)


if __name__ == "__main__":
    main()
