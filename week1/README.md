# Real-Time News Claim Verification System

**AI League #1 – RAG / Agentic RAG Hackathon**

A RAG-powered system that verifies news claims in real time. Highlight any text on the web, right-click "Verify Claim", and get a cited verdict: **True**, **False**, **Misleading**, or **Not Enough Evidence**.

---

## Architecture

```
User → Browser Extension → FastAPI Backend
                            ├── Claim Extraction (GPT-4o-mini)
                            ├── Claim Decomposition (GPT-4o-mini)
                            ├── Hybrid Retrieval
                            │   ├── ChromaDB (dense vector search)
                            │   ├── BM25 (sparse keyword search)
                            │   └── Tavily API (live web search)
                            ├── Cross-Encoder Reranking
                            ├── Agentic Loop (multi-round if insufficient)
                            ├── LLM Verification (GPT-4o)
                            └── Citation Validation
```

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
| LLM | GPT-4o / GPT-4o-mini (OpenAI) |
| Embedding | text-embedding-3-small (OpenAI) |
| Vector DB | ChromaDB (local, persistent) |
| Reranker | cross-encoder/ms-marco-MiniLM-L-6-v2 |
| Web Search | Tavily Search API |
| Frontend | Chrome Extension (MV3) / Web App |

## RAG Design

- **Chunking**: 512 tokens, 64-token overlap, recursive splitting
- **Retrieval**: Hybrid (dense + BM25) with Reciprocal Rank Fusion
- **Reranking**: Cross-encoder for deep relevance scoring
- **Agentic loop**: Up to 3 retrieval rounds with query reformulation
- **Citation validation**: Post-hoc fuzzy matching against retrieved evidence

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
│   │   ├── main.py              # FastAPI application
│   │   ├── config.py            # Settings from .env
│   │   ├── models.py            # Pydantic models
│   │   ├── services/
│   │   │   ├── agent.py         # Agentic pipeline controller
│   │   │   ├── claim_extractor.py
│   │   │   ├── embedder.py      # OpenAI embeddings + ChromaDB
│   │   │   ├── reasoner.py      # LLM verification logic
│   │   │   ├── reranker.py      # Cross-encoder reranking
│   │   │   ├── retriever.py     # Hybrid retrieval (dense + BM25)
│   │   │   ├── web_search.py    # Tavily API integration
│   │   │   └── citation_validator.py
│   │   └── knowledge_base/
│   │       ├── ingest.py        # KB ingestion pipeline
│   │       └── sources.py       # Credibility scoring
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
