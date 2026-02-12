# Phase 2 Architecture - Data Update System

## High-Level Overview

```mermaid
flowchart TB
    subgraph External["External Data Sources"]
        RSS["RSS Feeds<br/>(Reuters, AP, BBC)"]
        Wiki["Wikipedia API<br/>(50 key topics)"]
    end

    subgraph Automation["Update Automation"]
        Cron["Cron / Scheduler"]
        Daily["Daily Update<br/>(2 AM)"]
        Weekly["Weekly Update<br/>(Sunday 3 AM)"]
        Health["Health Check<br/>(12 PM)"]
    end

    subgraph Core["Core Update Service"]
        Fetcher["data_updater.py"]
        RSSFunc["fetch_rss_feeds()"]
        WikiFunc["fetch_wikipedia_articles()"]
        Cleanup["cleanup_expired_documents()"]
    end

    subgraph Ingestion["Ingestion Pipeline"]
        Chunk["Chunk Text<br/>(2000 chars, 250 overlap)"]
        Embed["Generate Embeddings<br/>(OpenAI text-embedding-3-small)"]
        Meta["Add Metadata<br/>(TTL, timestamps, credibility)"]
    end

    subgraph Storage["Knowledge Base"]
        ChromaDB[("ChromaDB<br/>Persistent Storage")]
    end

    subgraph Monitoring["Monitoring & Alerts"]
        Monitor["monitor_kb_health.py"]
        Alerts["Alerts<br/>(staleness, coverage)"]
    end

    RSS --> RSSFunc
    Wiki --> WikiFunc

    Cron --> Daily
    Cron --> Weekly
    Cron --> Health

    Daily --> RSSFunc
    Daily --> Cleanup
    Weekly --> WikiFunc

    RSSFunc --> Fetcher
    WikiFunc --> Fetcher
    Cleanup --> ChromaDB

    Fetcher --> Chunk
    Chunk --> Embed
    Embed --> Meta
    Meta --> ChromaDB

    Health --> Monitor
    Monitor --> ChromaDB
    Monitor --> Alerts

    style External fill:#e1f5ff
    style Automation fill:#fff4e1
    style Core fill:#e8f5e9
    style Ingestion fill:#f3e5f5
    style Storage fill:#ffebee
    style Monitoring fill:#fff9c4
```

## Data Flow Diagram

```mermaid
sequenceDiagram
    participant Cron
    participant Script as Update Script
    participant Updater as data_updater.py
    participant External as RSS/Wikipedia
    participant Ingest as ingest.py
    participant DB as ChromaDB
    participant Monitor as Health Monitor

    Note over Cron,Monitor: Daily Update Flow

    Cron->>Script: Trigger daily update (2 AM)
    Script->>Updater: run_daily_update()

    Updater->>External: Fetch RSS feeds
    External-->>Updater: Return articles

    Updater->>Ingest: ingest_documents(articles)
    Ingest->>Ingest: Chunk text
    Ingest->>Ingest: Generate embeddings
    Ingest->>Ingest: Add TTL metadata
    Ingest->>DB: Store chunks with metadata

    Updater->>DB: cleanup_expired_documents()
    DB-->>Updater: Deleted count

    Updater-->>Script: Stats (fetched, ingested, deleted)
    Script->>Monitor: Run health check
    Monitor->>DB: Query metadata
    DB-->>Monitor: Return stats
    Monitor-->>Script: Health status

    Script->>Cron: Complete (exit code 0/1)
```

## TTL Management System

```mermaid
flowchart LR
    subgraph Ingestion["Document Ingestion"]
        Doc["New Document"]
        Type{"Content<br/>Type?"}
    end

    subgraph TTL["TTL Assignment"]
        News["News Article<br/>TTL: 30 days"]
        Wiki["Wikipedia<br/>TTL: 90 days"]
        Fact["Fact-Check<br/>TTL: Never"]
        Gov["Government<br/>TTL: 180 days"]
    end

    subgraph Storage["Storage with Metadata"]
        DB[("ChromaDB")]
        Meta["Metadata:<br/>• ingested_at<br/>• expires_at<br/>• last_verified"]
    end

    subgraph Cleanup["Automated Cleanup"]
        Cron["Daily Cron Job"]
        Check{"Expired?<br/>(now > expires_at)"}
        Delete["Delete Document"]
    end

    Doc --> Type
    Type -->|"category: news"| News
    Type -->|"category: wiki"| Wiki
    Type -->|"category: fact_check"| Fact
    Type -->|"category: government"| Gov

    News --> Meta
    Wiki --> Meta
    Fact --> Meta
    Gov --> Meta

    Meta --> DB

    Cron --> Check
    DB --> Check
    Check -->|"Yes"| Delete
    Delete --> DB
    Check -->|"No"| DB

    style Ingestion fill:#e1f5ff
    style TTL fill:#fff4e1
    style Storage fill:#ffebee
    style Cleanup fill:#e8f5e9
```

## Source Credibility Scoring

```mermaid
flowchart TB
    subgraph Input["Input Source"]
        URL["Source URL"]
    end

    subgraph Scoring["Credibility Scoring"]
        Parse["Parse Domain"]
        Match{"Match<br/>Known<br/>Source?"}

        subgraph Tiers["Credibility Tiers"]
            T1["Tier 1: 0.95<br/>(Reuters, AP, BBC, NYT)"]
            T2["Tier 2: 0.85<br/>(CNN, Guardian, NPR)"]
            T3["Tier 3: 0.75<br/>(NBC, CBS, Politico)"]
            T4["Unknown: 0.60<br/>(Default)"]
        end
    end

    subgraph Output["Metadata"]
        Score["credibility_score"]
        Store["Store in ChromaDB"]
    end

    URL --> Parse
    Parse --> Match
    Match -->|"Tier 1 Domain"| T1
    Match -->|"Tier 2 Domain"| T2
    Match -->|"Tier 3 Domain"| T3
    Match -->|"Unknown"| T4

    T1 --> Score
    T2 --> Score
    T3 --> Score
    T4 --> Score

    Score --> Store

    style Input fill:#e1f5ff
    style Scoring fill:#fff4e1
    style Tiers fill:#f3e5f5
    style Output fill:#ffebee
```

## Health Monitoring System

```mermaid
flowchart TB
    subgraph Trigger["Trigger"]
        Cron["Daily Cron (12 PM)"]
        Manual["Manual Execution"]
    end

    subgraph Monitor["Health Monitor"]
        Script["monitor_kb_health.py"]
        Query["Query ChromaDB"]
    end

    subgraph Metrics["Metrics Collection"]
        Fresh["Data Freshness<br/>(newest document age)"]
        Cat["Category Distribution<br/>(fact_check, news, wiki)"]
        Exp["Expired Documents<br/>(count)"]
        Total["Total Chunks"]
    end

    subgraph Analysis["Health Analysis"]
        Check1{"Newest > 48h?"}
        Check2{"Category < 100?"}
        Check3{"Expired > 0?"}
    end

    subgraph Output["Output"]
        Report["Health Report"]
        Alert["Alerts"]
        Exit["Exit Code<br/>(0=healthy, 1=alerts, 2=error)"]
    end

    Cron --> Script
    Manual --> Script
    Script --> Query

    Query --> Fresh
    Query --> Cat
    Query --> Exp
    Query --> Total

    Fresh --> Check1
    Cat --> Check2
    Exp --> Check3

    Check1 -->|"Yes"| Alert
    Check2 -->|"Yes"| Alert
    Check3 -->|"Yes"| Alert

    Check1 -->|"No"| Report
    Check2 -->|"No"| Report
    Check3 -->|"No"| Report

    Alert --> Exit
    Report --> Exit

    style Trigger fill:#fff4e1
    style Monitor fill:#e1f5ff
    style Metrics fill:#f3e5f5
    style Analysis fill:#fff9c4
    style Output fill:#e8f5e9
```

## Smart Update Logic (Differential Re-Embedding)

```mermaid
flowchart TB
    subgraph Input["Update Trigger"]
        Source["Document URL"]
        New["New Content"]
    end

    subgraph Check["Content Comparison"]
        Fetch["Get Existing<br/>content_hash"]
        Compute["Compute New<br/>content_hash"]
        Compare{"Hashes<br/>Match?"}
    end

    subgraph Actions["Update Actions"]
        MetaOnly["Update Metadata Only<br/>(last_verified timestamp)"]
        Full["Full Re-Embedding<br/>(delete old + re-ingest)"]
    end

    subgraph Save["Save Changes"]
        DB[("ChromaDB")]
    end

    Source --> Fetch
    New --> Compute

    Fetch --> Compare
    Compute --> Compare

    Compare -->|"Yes<br/>(unchanged)"| MetaOnly
    Compare -->|"No<br/>(changed)"| Full

    MetaOnly --> DB
    Full --> DB

    style Input fill:#e1f5ff
    style Check fill:#fff4e1
    style Actions fill:#f3e5f5
    style Save fill:#ffebee
```

## Complete Update Cycle

```mermaid
gantt
    title Weekly Update Cycle
    dateFormat YYYY-MM-DD
    axisFormat %a

    section Daily Updates
    RSS Feed Update       :done, rss1, 2026-02-12, 1d
    Cleanup              :done, clean1, 2026-02-12, 1d
    Health Check         :done, health1, 2026-02-12, 1d

    RSS Feed Update       :rss2, 2026-02-13, 1d
    Cleanup              :clean2, 2026-02-13, 1d
    Health Check         :health2, 2026-02-13, 1d

    RSS Feed Update       :rss3, 2026-02-14, 1d
    Cleanup              :clean3, 2026-02-14, 1d
    Health Check         :health3, 2026-02-14, 1d

    section Weekly Update
    Wikipedia Update     :crit, wiki, 2026-02-16, 1d
```

## File Architecture

```
week1/
│
├── backend/app/
│   ├── config.py                      # Phase 2 settings
│   ├── services/
│   │   └── data_updater.py           # Core update logic
│   └── knowledge_base/
│       └── ingest.py                  # Enhanced with TTL
│
├── scripts/
│   ├── update_kb_daily.py            # Daily orchestrator
│   ├── update_kb_weekly.py           # Weekly orchestrator
│   ├── monitor_kb_health.py          # Health monitoring
│   ├── run_scheduler.py              # Built-in scheduler
│   └── test_update_system.py         # Test suite
│
├── logs/                              # Auto-generated logs
│   ├── daily_update.log
│   ├── weekly_update.log
│   └── health_check.log
│
├── data/chroma_db/                    # Knowledge base storage
│
├── crontab.example                    # Cron configuration
├── DATA_UPDATE_GUIDE.md              # Full documentation
└── PHASE2_QUICKREF.md                # Quick reference
```

## Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Update Service** | Python async | Core update logic |
| **RSS Parsing** | feedparser | Parse RSS feeds |
| **Wikipedia API** | wikipedia-api | Fetch Wikipedia articles |
| **Scheduling** | cron / schedule | Automate updates |
| **Storage** | ChromaDB | Vector database |
| **Embeddings** | OpenAI API | Generate embeddings |
| **Monitoring** | Python logging | Health checks & alerts |

## Key Design Decisions

### 1. TTL-Based Expiration
**Decision:** Use content-type-based TTL rather than uniform expiration

**Rationale:**
- Fact-checks are historical records (never expire)
- News becomes context after 30 days
- Wikipedia needs periodic refresh (90 days)
- Prevents unbounded storage growth

### 2. Hybrid Automation
**Decision:** Support both cron and built-in scheduler

**Rationale:**
- Cron for production (Linux/macOS)
- Built-in scheduler for development/Windows
- Flexibility for different deployment scenarios

### 3. Tiered Credibility
**Decision:** Pre-defined credibility tiers for sources

**Rationale:**
- Transparent source quality scoring
- Easy to audit and update
- Used in verification reasoning

### 4. Smart Re-Embedding
**Decision:** Hash-based change detection before re-embedding

**Rationale:**
- Saves API costs (embeddings)
- Reduces processing time
- Metadata-only updates for unchanged content

### 5. Health Monitoring
**Decision:** Separate health check script with alerts

**Rationale:**
- Proactive issue detection
- Independent of update process
- Actionable alerts (staleness, coverage)

## Performance Characteristics

### Update Frequency
- **Daily:** RSS feeds (50 articles) + cleanup
- **Weekly:** Wikipedia (50 articles)
- **Health:** Daily check

### Processing Times
- RSS update: 2-5 minutes
- Wikipedia update: 5-10 minutes
- Cleanup: < 1 minute
- Health check: < 30 seconds

### API Costs
- Daily RSS: $0.001 (embeddings)
- Weekly Wikipedia: $0.010 (embeddings)
- **Monthly total: ~$0.07**

### Storage Impact
- Daily growth: ~5MB (with cleanup)
- Weekly growth: ~20MB
- Stable state: 1-2GB (with TTL)

## Security Considerations

1. **API Keys:** Stored in `.env`, never in code
2. **Source Validation:** URL parsing and credibility scoring
3. **Rate Limiting:** Built-in delays for external APIs
4. **Input Sanitization:** Safe handling of fetched content
5. **Log Security:** Logs don't contain sensitive data

## Monitoring & Observability

### Logs
- Structured logging with timestamps
- Separate log files per component
- Rotation after 30 days

### Metrics Tracked
- Documents fetched/ingested
- Expired documents deleted
- Data staleness
- Category distribution
- Source coverage

### Alerts Triggered
- Data staleness > 48 hours
- Category coverage < 100 chunks
- Expired documents detected
- Update failures

## Scalability Path

### Current (Phase 2)
- Single-machine deployment
- Scheduled updates
- Local ChromaDB

### Future (Phase 3)
- Distributed updates (Celery workers)
- Event-driven updates (webhooks)
- Centralized monitoring (Prometheus)
- Cloud storage (managed vector DB)

---

**Architecture Version:** 1.0
**Last Updated:** 2026-02-12
**Status:** ✅ Implemented and Tested
