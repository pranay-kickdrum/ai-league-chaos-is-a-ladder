# Phase 2 Quick Reference Card

## 🚀 Quick Start

```bash
# Test everything works
python scripts/test_update_system.py

# Run daily update manually
python scripts/update_kb_daily.py

# Check health
python scripts/monitor_kb_health.py
```

## 📅 Automated Updates

### Using Cron (Production)

```bash
# Install
crontab crontab.example

# View
crontab -l

# Remove
crontab -r
```

### Using Scheduler (Development)

```bash
python scripts/run_scheduler.py
```

## 📊 What Gets Updated

| Update Type | Frequency | Content |
|------------|-----------|---------|
| **Daily** | Every day 2 AM | RSS feeds (Reuters, AP, BBC) + Cleanup |
| **Weekly** | Sunday 3 AM | Wikipedia (50 key topics) |
| **Health** | Every day 12 PM | Data freshness check |

## 🔧 Configuration Files

| File | Purpose |
|------|---------|
| `backend/app/config.py` | RSS feeds, Wikipedia topics, TTL settings |
| `crontab.example` | Cron schedule |
| `scripts/run_scheduler.py` | Alternative to cron |

## 📝 Important Settings

```python
# In backend/app/config.py

# TTL (days until expiration)
ttl_news_articles: int = 30
ttl_wikipedia: int = 90
ttl_fact_checks: int = 0  # Never expire

# Update frequency
rss_feed_check_hours: int = 24
wikipedia_update_days: int = 7

# Alerts
max_data_staleness_hours: int = 48
```

## 📂 File Structure

```
week1/
├── backend/app/services/
│   └── data_updater.py          # Update logic
├── scripts/
│   ├── update_kb_daily.py       # Daily update script
│   ├── update_kb_weekly.py      # Weekly update script
│   ├── monitor_kb_health.py     # Health check
│   ├── run_scheduler.py         # Alternative to cron
│   └── test_update_system.py    # Test all components
├── logs/                         # Created automatically
│   ├── daily_update.log
│   ├── weekly_update.log
│   └── health_check.log
├── crontab.example              # Cron configuration
└── DATA_UPDATE_GUIDE.md         # Full documentation
```

## 🩺 Health Check Output

```bash
$ python scripts/monitor_kb_health.py

✓ Total chunks: 15,432
📅 Newest: 3.5 hours ago
📊 Categories: fact_check (53%), news (29%), wiki (17%)
✓ No expired documents
✓ ALL SYSTEMS NOMINAL
```

## 🚨 Common Alerts

| Alert | Meaning | Fix |
|-------|---------|-----|
| Data is stale! | No new data > 48h | Run daily update |
| Low coverage | Category < 100 chunks | Add more sources |
| Expired documents | Docs past TTL | Run cleanup |

## 📖 View Logs

```bash
# Daily updates
tail -f logs/daily_update.log

# Weekly updates
tail -f logs/weekly_update.log

# All logs
tail -f logs/*.log
```

## 💰 Costs

| Update | Monthly | Annual |
|--------|---------|--------|
| Daily (RSS) | $0.03 | $0.36 |
| Weekly (Wikipedia) | $0.04 | $0.48 |
| **Total** | **~$0.07** | **~$0.84** |

Negligible! 🎉

## 🔍 Troubleshooting

```bash
# Test RSS feeds
python -c "
import asyncio
from app.services.data_updater import fetch_rss_feeds
docs = asyncio.run(fetch_rss_feeds())
print(f'Fetched {len(docs)} articles')
"

# Test Wikipedia
python -c "
import asyncio
from app.services.data_updater import fetch_wikipedia_articles
docs = asyncio.run(fetch_wikipedia_articles(['Climate_change']))
print(f'Fetched {len(docs)} articles')
"

# Check ChromaDB
python -c "
from app.services.embedder import get_collection
collection = get_collection()
print(f'Total chunks: {collection.count()}')
"
```

## 🎯 Customization

### Add RSS Feeds

Edit `backend/app/config.py`:

```python
rss_feeds: list[str] = [
    "https://feeds.reuters.com/reuters/topNews",
    "https://your-feed.com/rss",  # Add yours
]
```

### Add Wikipedia Topics

```python
wikipedia_topics: list[str] = [
    "Joe_Biden",
    "Your_Topic_Here",  # Use underscores
]
```

### Change TTL

```python
ttl_news_articles: int = 60  # Keep news 60 days instead of 30
```

## ⚡ Quick Commands

```bash
# Everything at once
python scripts/test_update_system.py && \
python scripts/monitor_kb_health.py

# Force updates now
python scripts/update_kb_daily.py && \
python scripts/update_kb_weekly.py

# Clean up expired
python -c "from app.services.data_updater import cleanup_expired_documents; print(f'Deleted: {cleanup_expired_documents()}')"
```

## 📚 Learn More

- Full guide: [DATA_UPDATE_GUIDE.md](./DATA_UPDATE_GUIDE.md)
- Main README: [README.md](./README.md)
- Architecture: [DETAILED_BACKEND_FLOW.md](./DETAILED_BACKEND_FLOW.md)

---

**Pro Tip:** Run `python scripts/test_update_system.py` after any configuration changes to verify everything works! ✅
