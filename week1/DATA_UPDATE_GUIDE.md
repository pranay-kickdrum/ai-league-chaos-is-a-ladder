# Knowledge Base Data Update System - Phase 2

This guide covers the Phase 2 implementation for keeping your knowledge base fresh with automated updates.

## Overview

The system keeps your ChromaDB knowledge base up-to-date through:

1. **Daily RSS Feed Updates** - Fetch latest news from trusted sources
2. **Weekly Wikipedia Updates** - Refresh political and current event topics
3. **TTL-Based Cleanup** - Remove expired documents automatically
4. **Health Monitoring** - Track data freshness and alert on issues

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Update System                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐ │
│  │ Daily Update │    │Weekly Update │    │   Cleanup    │ │
│  │  (RSS Feeds) │    │ (Wikipedia)  │    │  (TTL-based) │ │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘ │
│         │                   │                   │          │
│         └───────────────────┴───────────────────┘          │
│                             ▼                               │
│                    ┌─────────────────┐                      │
│                    │   ChromaDB KB   │                      │
│                    └─────────────────┘                      │
│                             ▲                               │
│                    ┌────────┴────────┐                      │
│                    │ Health Monitor  │                      │
│                    └─────────────────┘                      │
└─────────────────────────────────────────────────────────────┘
```

## Features

### 1. RSS Feed Polling

**Frequency:** Daily (configurable)

**Sources:**
- Reuters Top News
- Associated Press
- BBC News

**Configuration:** Edit `backend/app/config.py`:

```python
rss_feeds: list[str] = [
    "https://feeds.reuters.com/reuters/topNews",
    "https://www.ap.org/rss",
    "https://feeds.bbci.co.uk/news/rss.xml",
    # Add more feeds here
]
```

**Source Credibility Scoring:**
- Tier 1 (0.95): Reuters, AP, BBC, NYT, WSJ
- Tier 2 (0.85): CNN, Guardian, NPR, Bloomberg
- Tier 3 (0.75): NBC, CBS, ABC, Politico
- Unknown (0.60): Default for new sources

### 2. Wikipedia Updates

**Frequency:** Weekly (configurable)

**Topics:** 50 key political and current event articles

**Configuration:** Edit `backend/app/config.py`:

```python
wikipedia_topics: list[str] = [
    "Joe_Biden",
    "Climate_change",
    "Artificial_intelligence",
    # ... add more topics
]
```

### 3. TTL (Time-To-Live) Management

Different content types have different expiration periods:

| Content Type | TTL | Rationale |
|-------------|-----|-----------|
| Fact-checks | Never | Historical record |
| News articles | 30 days | Events become context |
| Wikipedia | 90 days | Quarterly updates |
| Government data | 180 days | Stable content |

**Metadata Structure:**

```python
{
    "ingested_at": "2026-02-12T10:00:00Z",
    "expires_at": "2026-03-12T10:00:00Z",
    "last_verified": "2026-02-12T10:00:00Z",
    "is_historical": False,
    "source_type": "rss_feed",
}
```

### 4. Health Monitoring

**Metrics Tracked:**
- Data staleness (newest document age)
- Category distribution
- Source coverage
- Expired document count
- Total chunks

**Alerts Triggered When:**
- Newest data > 48 hours old
- Category has < 100 sources
- Expired documents detected

## Installation

1. **Install dependencies:**

```bash
cd week1/backend
pip install -r requirements.txt
```

New dependencies added:
- `feedparser` - RSS feed parsing
- `wikipedia-api` - Wikipedia article fetching
- `schedule` - Job scheduling

2. **Create logs directory:**

```bash
cd week1
mkdir -p logs
```

3. **Make scripts executable:**

```bash
chmod +x scripts/*.py
```

## Usage

### Manual Updates

#### Run Daily Update (RSS + Cleanup)

```bash
cd week1
python scripts/update_kb_daily.py
```

#### Run Weekly Update (Wikipedia)

```bash
cd week1
python scripts/update_kb_weekly.py
```

#### Check Knowledge Base Health

```bash
cd week1
python scripts/monitor_kb_health.py
```

### Automated Updates (Recommended)

#### Option A: Using Cron (Linux/macOS)

1. Edit the example crontab:

```bash
# Update PROJECT_PATH in crontab.example to your actual path
nano crontab.example
```

2. Install the crontab:

```bash
crontab crontab.example
```

3. Verify cron jobs:

```bash
crontab -l
```

**Default Schedule:**
- Daily update: Every day at 2:00 AM
- Weekly update: Every Sunday at 3:00 AM
- Health check: Every day at 12:00 PM

#### Option B: Using the Built-in Scheduler

Run as a long-lived process:

```bash
cd week1
python scripts/run_scheduler.py
```

This is useful for:
- Development/testing
- Systems without cron
- Windows environments

To run in background:

```bash
nohup python scripts/run_scheduler.py > logs/scheduler.log 2>&1 &
```

## Configuration

### Update Frequencies

Edit `backend/app/config.py`:

```python
# Update intervals
rss_feed_check_hours: int = 24       # Check daily
wikipedia_update_days: int = 7       # Update weekly
cleanup_check_hours: int = 24        # Daily cleanup

# Data health monitoring
max_data_staleness_hours: int = 48  # Alert threshold
min_sources_per_category: int = 100  # Coverage threshold
```

### TTL Periods

```python
# TTL (in days) for different content types
ttl_news_articles: int = 30
ttl_wikipedia: int = 90
ttl_fact_checks: int = 0            # Never expire
ttl_government_data: int = 180
```

### RSS Feeds

Add/remove feeds as needed:

```python
rss_feeds: list[str] = [
    "https://feeds.reuters.com/reuters/topNews",
    "https://www.ap.org/rss",
    "https://feeds.bbci.co.uk/news/rss.xml",
    # Add your feeds here
]
```

**Finding RSS Feeds:**
- Most news sites have `/rss` or `/feed` endpoints
- Check footer or "Subscribe" sections
- Use RSS aggregators like Feedly to discover feeds

### Wikipedia Topics

Customize topics based on your focus:

```python
wikipedia_topics: list[str] = [
    # Politics
    "Joe_Biden", "Donald_Trump",
    # Technology
    "Artificial_intelligence", "Cryptocurrency",
    # Health
    "COVID-19_pandemic", "Healthcare_in_the_United_States",
    # Add your topics here (use underscores for spaces)
]
```

## Monitoring

### View Update Logs

```bash
# Daily updates
tail -f logs/daily_update.log

# Weekly updates
tail -f logs/weekly_update.log

# Health checks
tail -f logs/health_check.log
```

### Health Check Output

```
================================================================================
KNOWLEDGE BASE HEALTH CHECK
================================================================================

✓ Total chunks in knowledge base: 15,432

📅 Data Freshness:
  Newest document: 2026-02-12 08:30:45
  Oldest document: 2026-01-15 10:00:00
  Staleness: 3.5 hours

📊 Category Distribution:
  fact_check           :  8,234 ( 53.4%)
  news                 :  4,521 ( 29.3%)
  wiki                 :  2,677 ( 17.3%)

📰 Top Sources:
  LIAR / PolitiFact           :  8,234 ( 53.4%)
  Reuters                      :  1,245 (  8.1%)
  Wikipedia                    :  2,677 ( 17.3%)

✓ No expired documents

================================================================================
✓ HEALTH CHECK: ALL SYSTEMS NOMINAL
================================================================================
```

### Alerts

When issues are detected:

```
⚠ HEALTH CHECK: 2 ALERT(S)
  - 🚨 ALERT: Data is stale! Newest document is 52.3 hours old (threshold: 48h)
  - ⚠ Low coverage for category 'news': 45 chunks (threshold: 100)
```

## Troubleshooting

### Issue: RSS feeds failing

**Symptoms:** `✗ Failed to fetch` errors in logs

**Solutions:**
1. Check internet connectivity
2. Verify RSS feed URLs are valid (test in browser)
3. Check for rate limiting (add delays between feeds)
4. Some feeds require User-Agent headers

### Issue: Wikipedia API rate limiting

**Symptoms:** Slow updates or timeout errors

**Solutions:**
1. Reduce number of topics in `wikipedia_topics`
2. Add delays between requests
3. Wikipedia API is generally permissive for educational use

### Issue: Cron jobs not running

**Symptoms:** No log files created, data not updating

**Solutions:**
1. Check cron is running: `service cron status` (Linux) or check System Preferences (macOS)
2. Verify paths in crontab are absolute
3. Test script manually first: `python scripts/update_kb_daily.py`
4. Check cron logs: `grep CRON /var/log/syslog` (Linux) or `log show --predicate 'eventMessage contains "cron"' --last 1h` (macOS)

### Issue: Memory issues during updates

**Symptoms:** Process killed, out of memory errors

**Solutions:**
1. Reduce batch sizes in `ingest_documents()`
2. Limit number of RSS feeds or Wikipedia topics
3. Run updates sequentially instead of all at once

### Issue: ChromaDB permissions

**Symptoms:** Permission denied errors

**Solutions:**
1. Check ownership: `ls -la data/chroma_db/`
2. Fix permissions: `chmod -R 755 data/chroma_db/`
3. Ensure cron runs as correct user

## Advanced Features

### Differential Re-Embedding

The system includes smart update logic that avoids re-embedding unchanged content:

```python
from app.services.data_updater import smart_update_document

# Only re-embeds if content hash changes
await smart_update_document(url, new_text, metadata)
```

This saves:
- API costs (OpenAI embeddings)
- Processing time
- Storage

### Custom Update Logic

Create custom update scripts:

```python
# scripts/custom_update.py
import asyncio
from app.services.data_updater import fetch_rss_feeds
from app.knowledge_base.ingest import ingest_documents

async def custom_update():
    # Fetch from custom sources
    custom_feeds = ["https://your-feed.com/rss"]
    docs = await fetch_rss_feeds(custom_feeds)

    # Ingest with custom settings
    ingest_documents(docs, source_label="custom_source")

asyncio.run(custom_update())
```

### Email Alerts

Set up email notifications for failures (requires `mailx`):

```bash
# In crontab:
0 2 * * * cd $PROJECT_PATH && python scripts/update_kb_daily.py || \
  echo "Daily update failed on $(date)" | \
  mail -s "KB Update Alert" your-email@example.com
```

## Best Practices

1. **Start Small:** Begin with a few RSS feeds and Wikipedia topics, then expand
2. **Monitor First Week:** Watch logs daily for the first week to catch issues
3. **Test Updates Manually:** Run scripts manually before setting up cron
4. **Set Up Alerts:** Configure email or Slack alerts for failures
5. **Regular Health Checks:** Review health check output weekly
6. **Log Rotation:** Set up log rotation to prevent disk space issues
7. **Backup Before Updates:** Consider backing up ChromaDB before major updates

## Performance Considerations

### Update Times

Typical update durations:
- Daily update (50 RSS articles): 2-5 minutes
- Weekly update (50 Wikipedia articles): 5-10 minutes
- Cleanup: < 1 minute
- Health check: < 30 seconds

### API Costs

Estimated costs (using OpenAI embeddings):

| Update Type | Tokens | Cost (text-embedding-3-small) |
|------------|--------|-------------------------------|
| 50 RSS articles | ~50k | $0.001 |
| 50 Wikipedia articles | ~500k | $0.010 |
| **Monthly Total** | ~2M | ~$0.04 |

Very affordable! The static LIAR dataset is embedded once during initial setup.

### Storage Growth

Approximate storage per update:
- 50 RSS articles: ~5MB in ChromaDB
- 50 Wikipedia articles: ~20MB in ChromaDB
- Monthly growth: ~200MB

With 30-day TTL for news, storage stabilizes around 1-2GB.

## Next Steps (Phase 3)

Consider these enhancements for production:

1. **Event-Driven Updates:** Webhooks from news APIs for real-time updates
2. **Fact-Check API Integration:** Google Fact Check Tools API polling
3. **Task Queue:** Use Celery or RQ for better job management
4. **Distributed Updates:** Multiple workers for parallel processing
5. **Advanced Monitoring:** Prometheus + Grafana dashboards
6. **ML-Based Relevance Filtering:** Only ingest highly relevant articles

## Support

For issues or questions:
1. Check logs: `tail -f logs/*.log`
2. Run health check: `python scripts/monitor_kb_health.py`
3. Review this guide
4. Check project README

## Summary

Phase 2 provides a robust, low-maintenance system to keep your knowledge base fresh:

✅ **Automated updates** via cron or built-in scheduler
✅ **Smart TTL management** prevents stale data
✅ **Health monitoring** catches issues early
✅ **Cost-effective** (~$0.04/month for embeddings)
✅ **Configurable** to your specific needs

Your claim verification system now has evergreen, up-to-date knowledge! 🎉
