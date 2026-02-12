#!/usr/bin/env python3
"""Knowledge base health monitoring script.

Checks:
  - Data staleness (newest document timestamp)
  - Source distribution
  - Expired documents count
  - Category coverage
  - Total document count

Alerts if issues are detected (newest data > 48 hours old, etc.)
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.config import settings
from app.services.embedder import get_collection


def check_kb_health() -> dict:
    """Perform health check on the knowledge base.

    Returns:
        Dict with health statistics and alerts.
    """
    print("\n" + "=" * 80)
    print("KNOWLEDGE BASE HEALTH CHECK")
    print("=" * 80)

    try:
        collection = get_collection()

        # Get all documents with metadata
        results = collection.get(include=["metadatas"])

        if not results or not results["ids"]:
            print("⚠ WARNING: Knowledge base is empty!")
            return {"status": "empty", "total_chunks": 0}

        total_chunks = len(results["ids"])
        metadatas = results["metadatas"]

        print(f"\n✓ Total chunks in knowledge base: {total_chunks:,}")

        # Analyze metadata
        stats = {
            "total_chunks": total_chunks,
            "categories": {},
            "sources": {},
            "ingested_dates": [],
            "expired_count": 0,
            "alerts": [],
        }

        now = datetime.now()

        for metadata in metadatas:
            # Category distribution
            category = metadata.get("category", "unknown")
            stats["categories"][category] = stats["categories"].get(category, 0) + 1

            # Source distribution
            source_name = metadata.get("source_name", "unknown")
            stats["sources"][source_name] = stats["sources"].get(source_name, 0) + 1

            # Ingestion timestamps
            ingested_at = metadata.get("ingested_at")
            if ingested_at and ingested_at != "unknown":
                try:
                    stats["ingested_dates"].append(datetime.fromisoformat(ingested_at))
                except Exception:
                    pass

            # Expired documents
            expires_at = metadata.get("expires_at")
            if expires_at and expires_at != "never":
                try:
                    expiry_date = datetime.fromisoformat(expires_at)
                    if expiry_date < now:
                        stats["expired_count"] += 1
                except Exception:
                    pass

        # Calculate freshness
        if stats["ingested_dates"]:
            newest = max(stats["ingested_dates"])
            oldest = min(stats["ingested_dates"])
            staleness_hours = (now - newest).total_seconds() / 3600

            stats["newest_ingested"] = newest.isoformat()
            stats["oldest_ingested"] = oldest.isoformat()
            stats["staleness_hours"] = staleness_hours

            print(f"\n📅 Data Freshness:")
            print(f"  Newest document: {newest.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"  Oldest document: {oldest.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"  Staleness: {staleness_hours:.1f} hours")

            # Alert if data is too stale
            if staleness_hours > settings.max_data_staleness_hours:
                alert = f"🚨 ALERT: Data is stale! Newest document is {staleness_hours:.1f} hours old (threshold: {settings.max_data_staleness_hours}h)"
                stats["alerts"].append(alert)
                print(f"\n{alert}")
        else:
            print("\n⚠ WARNING: No ingestion timestamps found")
            stats["alerts"].append("No ingestion timestamps found")

        # Category breakdown
        print(f"\n📊 Category Distribution:")
        for category, count in sorted(stats["categories"].items(), key=lambda x: x[1], reverse=True):
            percentage = (count / total_chunks) * 100
            print(f"  {category:20s}: {count:6,} ({percentage:5.1f}%)")

            # Alert if category has too few sources
            if count < settings.min_sources_per_category and category != "unknown":
                alert = f"⚠ Low coverage for category '{category}': {count} chunks (threshold: {settings.min_sources_per_category})"
                stats["alerts"].append(alert)

        # Source breakdown (top 10)
        print(f"\n📰 Top Sources:")
        sorted_sources = sorted(stats["sources"].items(), key=lambda x: x[1], reverse=True)
        for source_name, count in sorted_sources[:10]:
            percentage = (count / total_chunks) * 100
            print(f"  {source_name:30s}: {count:6,} ({percentage:5.1f}%)")

        # Expired documents
        if stats["expired_count"] > 0:
            percentage = (stats["expired_count"] / total_chunks) * 100
            print(f"\n⚠ Expired documents: {stats['expired_count']:,} ({percentage:.1f}%)")
            alert = f"Cleanup recommended: {stats['expired_count']} expired documents"
            stats["alerts"].append(alert)
        else:
            print(f"\n✓ No expired documents")

        # Summary
        print("\n" + "=" * 80)
        if stats["alerts"]:
            print(f"⚠ HEALTH CHECK: {len(stats['alerts'])} ALERT(S)")
            for alert in stats["alerts"]:
                print(f"  - {alert}")
        else:
            print("✓ HEALTH CHECK: ALL SYSTEMS NOMINAL")
        print("=" * 80 + "\n")

        stats["status"] = "alerts" if stats["alerts"] else "healthy"
        return stats

    except Exception as exc:
        print(f"\n✗ Health check failed: {exc}")
        return {"status": "error", "error": str(exc)}


def main():
    """Run health check and exit with appropriate code."""
    stats = check_kb_health()

    # Exit codes
    # 0 = healthy
    # 1 = alerts
    # 2 = error
    if stats["status"] == "error":
        sys.exit(2)
    elif stats["status"] == "alerts":
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
