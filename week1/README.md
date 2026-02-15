# Real-Time News Claim Verification System

**AI League #1 – RAG / Agentic RAG Hackathon**

A RAG-powered system that verifies news claims in real time. Highlight any text on the web, right-click "Verify Claim", and get a cited verdict: **True**, **False**, **Misleading**, or **Not Enough Evidence**.

---

## Architecture (Backend Pipeline)

The backend runs a 6-step pipeline orchestrated by `agent.py`. Steps 2-4 form the **core RAG pipeline** (Retrieval-Augmented Generation).

```
POST /api/verify (raw text)
│
├── Step 1: Claim Extraction + Decomposition        [PRE-PROCESSING]
│   └── GPT-4o-mini or heuristic fast-path
│       Extracts core claim, splits into atomic sub-claims
│
├── Step 2: Evidence Retrieval                       [RAG: Retrieval]
│   ├── Dense vector search (ChromaDB, top-20)
│   ├── BM25 keyword search (in-memory, top-20)
│   ├── Reciprocal Rank Fusion (k=60)
│   ├── Cross-Encoder Reranking (ms-marco-MiniLM, top-5)
│   ├── Sufficiency check (top_score > 0.5)
│   └── Web fallback (Tavily API) + query reformulation (max 2 rounds)
│
├── Step 3: Evidence Consolidation                   [RAG: Augmentation]
│   └── Deduplicate, filter, fallback search, sort by relevance
│
├── Step 4: LLM Reasoning + Verification             [RAG: Generation]
│   └── GPT-4o-mini generates verdict + reasoning from top-5 evidence
│   └── (4b) Web retry if NOT_ENOUGH_EVIDENCE and no web used
│
├── Step 5: Citation Validation                      [RAG: Guardrail]
│   └── Fuzzy-match citations to evidence, filter hallucinated sources
│
└── Step 6: Feedback Loop                            [RAG: Self-Improvement]
    └── Store verified claims back into ChromaDB for future queries
│
└── VerifyResponse JSON (verdict + confidence + reasoning + citations)
```

For detailed architecture diagrams, see [DETAILED_BACKEND_FLOW.md](./DETAILED_BACKEND_FLOW.md). For technical explanations of each component, see [TECHNICAL_EXPLANATION.md](./TECHNICAL_EXPLANATION.md).

## Quick Start

### 1. Setup Environment

```bash
cd week1
python -m venv venv
source venv/bin/activate    # Windows: venv\Scripts\activate
pip install -r backend/requirements.txt
```

### 2. Configure API Keys

```bash
cd backend
cp .env.example .env
# Edit .env with your API keys:
```

Required keys in `.env`:
```
OPENAI_API_KEY=sk-...        # Get from https://platform.openai.com/api-keys
TAVILY_API_KEY=tvly-...      # Get from https://tavily.com
```

### 3. Ingest Knowledge Base (Recommended)

The system needs a knowledge base to verify claims. Ingest the LIAR fact-checking dataset:

```bash
cd week1
python scripts/ingest_kb.py --liar
```

This will:
- Load 1,267 fact-checked claims from the LIAR dataset
- Generate embeddings using OpenAI's text-embedding-3-small
- Store in ChromaDB at `week1/data/chroma_db`
- Takes ~2-3 minutes, costs ~$0.10 in API calls

**Note:** The dataset is included in `week1/data/liar_dataset/`. If you get a memory error, the system will batch-process automatically.

### 4. Start the Backend Server

```bash
cd week1
PYTHONPATH=backend uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at `http://localhost:8000`

Check health: `curl http://localhost:8000/health`

---

## Running the System

You have **two options** to use the claim verification system:

### Option A: Browser Extension (Recommended)

The Chrome extension lets you verify claims on any webpage by highlighting text.

**Installation:**

1. Open Chrome and go to `chrome://extensions/`
2. Enable **Developer mode** (toggle in top-right)
3. Click **Load unpacked**
4. Navigate to and select: `/path/to/week1/extension/`
5. The "Claim Verifier" extension should now appear in your toolbar

**Usage:**

1. Navigate to any news article or webpage
2. **Highlight/select** text containing a claim
3. **Right-click** → "Verify Claim: ..."
4. A popup appears **above your selection** showing:
   - Verdict: TRUE / FALSE / MISLEADING / NOT ENOUGH EVIDENCE
   - Confidence score
   - Reasoning
   - Source citations

**Alternative: Use the Extension Popup**

- Click the extension icon in your toolbar
- Paste or type a claim
- Click "Verify Claim"
- Results appear in the popup with scrollable details

**Troubleshooting:**
- If the popup doesn't appear, check the console at `chrome://extensions/` for errors
- Make sure the backend server is running at `http://localhost:8000`
- Reload the extension after code changes

---

### Option B: Standalone Web App

A simple web interface without needing to install an extension.

**Run:**

```bash
# Backend must be running (see step 4 above)
cd week1/webapp
# Option 1: Open directly
open index.html

# Option 2: Serve with Python
python -m http.server 8080
# Then visit: http://localhost:8080
```

**Usage:**

1. Open the web app in your browser
2. Paste or type a claim in the text area
3. Click "Verify Claim"
4. Results appear below with:
   - Verdict badge
   - Confidence score
   - Reasoning
   - Sub-claims (if any)
   - Source citations
   - Metadata (processing time, sources checked)

---

## Keeping Data Fresh (Phase 2)

Your knowledge base needs regular updates to stay current! Phase 2 implements automated data freshness:

### Quick Test

Test the update system:

```bash
cd week1
python scripts/test_update_system.py
```

### Setup Automated Updates

**Option A: Using Cron (Recommended for production)**

```bash
# Edit crontab.example with your path
nano crontab.example

# Install cron jobs
crontab crontab.example

# Verify
crontab -l
```

**Default Schedule:**
- **Daily (2 AM):** Fetch RSS news feeds + cleanup expired docs
- **Weekly (Sunday 3 AM):** Update Wikipedia articles
- **Daily (12 PM):** Health check

**Option B: Using Built-in Scheduler**

```bash
# Run as long-lived process
python scripts/run_scheduler.py
```

### Manual Updates

```bash
# Daily update (RSS feeds + cleanup)
python scripts/update_kb_daily.py

# Weekly update (Wikipedia)
python scripts/update_kb_weekly.py

# Health check
python scripts/monitor_kb_health.py
```

### Configuration

Edit `backend/app/config.py` to customize:
- RSS feed sources
- Wikipedia topics to monitor
- TTL periods (how long data stays fresh)
- Update frequencies

**📖 Full Guide:** See [DATA_UPDATE_GUIDE.md](./DATA_UPDATE_GUIDE.md) for complete documentation.

---

## Quick Demo

Once everything is running, try verifying this claim:

```
"The Earth is flat and NASA is hiding the truth."
```

Expected result:
- **Verdict:** FALSE
- **Confidence:** ~95%
- **Reasoning:** Debunks flat Earth claims with scientific evidence
- **Sources:** Wikipedia, fact-checking databases

---

## API

### `POST /api/verify`

**Request:**
```json
{
  "text": "The highlighted text to verify",
  "url": "https://source-page.com (optional)"
}
```

**Response:**
```json
{
  "claim": "Extracted core claim",
  "verdict": "TRUE | FALSE | MISLEADING | NOT_ENOUGH_EVIDENCE",
  "confidence": 0.87,
  "reasoning": "Step-by-step explanation...",
  "sub_claims": [...],
  "citations": [{"source_name": "...", "url": "...", "relevant_quote": "..."}],
  "metadata": {"processing_time_ms": 3200, "sources_checked": 12}
}
```

---

## Tech Stack

| Component | Technology |
|---|---|
| Backend | FastAPI (Python 3.11+) |
| LLM (reasoning + extraction) | GPT-4o-mini (OpenAI) |
| Embedding | text-embedding-3-small (OpenAI, 1536 dims) |
| Vector DB | ChromaDB (local, persistent, cosine similarity) |
| Sparse Search | BM25 via rank-bm25 (in-memory index) |
| Reranker | cross-encoder/ms-marco-MiniLM-L-6-v2 (sentence-transformers) |
| Web Search | Tavily Search API (cached 1hr, rate-limited) |
| Citation Validation | thefuzz (fuzzy string matching) |
| Frontend | Chrome Extension (MV3) / Web App |

## RAG Design

- **Chunking**: 2000-character chunks with 250-character overlap, paragraph-aware splitting (falls back to sentence boundaries)
- **Retrieval (the R)**: Hybrid search -- dense vector (ChromaDB cosine similarity) + BM25 keyword match -- merged via Reciprocal Rank Fusion (k=60). Dense catches semantic meaning, BM25 catches exact terms
- **Reranking**: Cross-encoder (`ms-marco-MiniLM-L-6-v2`) deeply scores each (query, passage) pair and keeps top-5
- **Agentic loop**: Up to 2 retrieval rounds with GPT-4o-mini query reformulation when KB evidence is insufficient; web search via Tavily API as fallback
- **Augmentation (the A)**: Evidence is deduplicated, filtered, and sorted by relevance; top-5 chunks (max 400 chars each) form the LLM context window
- **Generation (the G)**: GPT-4o-mini generates a structured verdict (TRUE/FALSE/MISLEADING/NOT_ENOUGH_EVIDENCE) grounded in retrieved evidence, not parametric memory
- **Citation validation**: Post-hoc fuzzy matching (`thefuzz` partial ratio, threshold 50) ensures every citation traces to real retrieved evidence; URLs validated for credibility >= 0.60
- **Feedback loop**: Verified claims (confidence >= 0.3) are stored back into ChromaDB, making the knowledge base self-improving over time

## Evaluation

```bash
# Server must be running
python scripts/evaluate.py --samples 20
```

Reports: accuracy, citation rate, hallucination rate, latency (p50/p95).

---

## Project Structure

```
week1/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry point + startup preloading
│   │   ├── config.py            # Settings from .env (models, thresholds, TTLs)
│   │   ├── models.py            # Pydantic models (VerifyRequest/Response, EvidenceChunk, etc.)
│   │   ├── services/
│   │   │   ├── agent.py         # Step 1-6 pipeline orchestrator
│   │   │   ├── claim_extractor.py  # Step 1: extraction + decomposition
│   │   │   ├── retriever.py     # Step 2: hybrid retrieval (dense + BM25 + RRF)
│   │   │   ├── embedder.py      # Step 2: OpenAI embeddings + ChromaDB operations
│   │   │   ├── reranker.py      # Step 2: cross-encoder reranking
│   │   │   ├── web_search.py    # Step 2: Tavily API (cached, rate-limited)
│   │   │   ├── reasoner.py      # Step 4: LLM verification + query reformulation
│   │   │   ├── citation_validator.py  # Step 5: fuzzy matching + credibility filtering
│   │   │   └── data_updater.py  # Data freshness: RSS/Wikipedia updates + TTL cleanup
│   │   └── knowledge_base/
│   │       ├── ingest.py        # KB ingestion pipeline (chunk, embed, store)
│   │       └── sources.py       # Source credibility scoring
│   ├── requirements.txt
│   └── .env.example
├── extension/                   # Chrome Extension (Manifest V3)
├── webapp/                      # Standalone web app (fallback)
├── scripts/
│   ├── ingest_kb.py             # Knowledge base ingestion
│   ├── evaluate.py              # Evaluation metrics
│   └── generate_icons.py        # Extension icon generator
└── data/                        # Datasets and ChromaDB storage
```

---

## Constraints

- Always cites sources from retrieved evidence
- Never fabricates sources (post-hoc validation strips ungrounded citations)
- Returns "Not Enough Evidence" when evidence is insufficient
- Fully demo-able via browser extension or web app
