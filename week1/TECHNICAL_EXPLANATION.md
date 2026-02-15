# Technical Explanation

Short technical explanation of each core component in the claim verification pipeline.

---

## 1. Embedding Model

| Property | Value |
|----------|-------|
| **Model** | OpenAI `text-embedding-3-small` |
| **Dimensions** | 1536 |
| **Batch size** | 10 documents per API call |

We chose a **text embedding** model (not a sentence embedding model) because the evidence passages are multi-sentence document chunks, not single sentences. `text-embedding-3-small` offers a good balance of cost, speed, and quality for semantic similarity search over mixed-length text.

All sub-claims are embedded in a **single batched API call** to avoid N separate round-trips. The resulting vectors are stored in ChromaDB and used for dense cosine-similarity retrieval.

---

## 2. Vector Database

| Property | Value |
|----------|-------|
| **Database** | ChromaDB (persistent, on-disk) |
| **Collection** | `knowledge_base` |
| **Distance function** | Cosine similarity (`hnsw:space: cosine`) |
| **Persist directory** | `week1/data/chroma_db` |

ChromaDB was chosen for its simplicity (no external server needed), Python-native API, and built-in persistence. It runs embedded in the FastAPI process. The HNSW index provides fast approximate nearest-neighbour search at scale.

Each document is stored with rich metadata: `source_name`, `source_url`, `category`, `publish_date`, `credibility_score`, and `doc_type`. This metadata is used downstream for citation building and credibility display.

---

## 3. Chunking Strategy

| Property | Value |
|----------|-------|
| **Chunk size** | 2000 characters |
| **Overlap** | 250 characters |
| **Strategy** | Paragraph → sentence → character boundaries |

The chunking algorithm (`chunk_text()` in `embedder.py`) uses a **hierarchical boundary preference**:

1. **Paragraph boundaries** (`\n\n`) — preferred split point to keep semantic units intact
2. **Sentence boundaries** (`. `) — fallback when paragraphs exceed chunk size
3. **Character split** — last resort for very long sentences

The 250-char overlap ensures that key facts spanning a chunk boundary are captured in at least one chunk. The 2000-char chunk size was chosen to fit comfortably within the embedding model's context window while keeping each chunk focused on a single topic.

---

## 4. Reranking Approach

| Property | Value |
|----------|-------|
| **Model** | `cross-encoder/ms-marco-MiniLM-L-6-v2` |
| **Type** | Cross-encoder (bidirectional attention) |
| **Top-k kept** | 5 |

The reranker is a critical second-stage filter. Unlike embedding-based retrieval (which encodes query and passage independently), the cross-encoder sees **both texts simultaneously** with full bidirectional attention. This catches nuanced relevance that cosine similarity misses.

**How it works:**
1. The retriever returns ~20 candidates from dense + sparse search
2. The cross-encoder scores each `(query, passage)` pair
3. Only the top-5 by score are kept for the LLM

This two-stage approach (fast recall via embeddings → precise ranking via cross-encoder) is the standard pattern in modern RAG systems. The MiniLM model is ~80 MB, runs locally, and adds minimal latency.

---

## 5. Knowledge Base Design + Live Web Validation

### Knowledge Base Sources

The KB contains three categories of content with different freshness policies:

| Source | Update Frequency | TTL | Credibility |
|--------|-----------------|-----|-------------|
| **RSS news feeds** (Reuters, AP, BBC) | Daily (24h) | 30 days | Domain-based (0.80–0.95) |
| **Wikipedia articles** (50 curated topics) | Weekly (7 days) | 90 days | 0.90 fixed |
| **Verified claims** (feedback loop) | On every verification | Never expires | Based on original confidence |

### Static GK vs Current Affairs

The system handles both **static general knowledge** and **current affairs** through its TTL (time-to-live) strategy:

- **Static GK** — Wikipedia articles on established facts (e.g. "India's independence year") have a 90-day TTL but the underlying facts rarely change. Fact-check results from verified claims **never expire** (TTL = 0), making them a permanent knowledge layer.
- **Current affairs** — RSS news articles expire after 30 days, ensuring stale news doesn't pollute results. The `data_updater.py` service runs on a schedule to ingest fresh articles.
- **Differential updates** — A content hash comparison avoids re-embedding unchanged content. Only genuinely new or modified articles are chunked and embedded.

### Live Web Validation Strategy

When the KB doesn't have enough evidence, the system falls back to **live web search** via Tavily API:

1. **Triggered when**: Cross-encoder top score < 0.5 or fewer than 2 relevant chunks
2. **Search**: Tavily advanced search returns top-5 results with extracted text
3. **Merge**: Web results are merged with KB evidence and re-reranked together
4. **Query reformulation**: If still insufficient, GPT-4o-mini rewrites the query (max 2 rounds)
5. **Last resort**: If the LLM returns NOT_ENOUGH_EVIDENCE and web was never tried, a final web search is triggered

**Safeguards:**
- In-memory cache (1-hour TTL) prevents duplicate API calls
- Token-bucket rate limiter (10 requests/minute)
- Web evidence is stored back into ChromaDB for future queries

### Source Credibility Scoring

Every source gets a credibility score (0.0–1.0) based on its domain:

| Tier | Score | Examples |
|------|-------|----------|
| Tier 1 | 0.95 | AP, Reuters, BBC, NYT, Wikipedia, WHO, CDC |
| Tier 2 | 0.80 | Guardian, NPR, PBS, PolitiFact, Snopes |
| Government | 0.80 | Any `.gov` domain |
| Academic | 0.80 | Any `.edu` domain |
| Unknown | 0.40 | Unrecognised domains |
| Unreliable | 0.20 | InfoWars, NaturalNews, The Onion |

This score is attached to every evidence chunk and displayed to the user alongside citations.

---

## 6. Verification / Validation Logic

The verification pipeline has 6 steps. Here is what each does and why:

### Step 1 — Claim Extraction + Decomposition
Isolates the core verifiable claim from raw text and splits compound claims into atomic sub-claims. Short simple inputs take a fast heuristic path; complex inputs go through GPT-4o-mini.

### Step 2 — Evidence Retrieval (RAG: Retrieval)
For each sub-claim:
- **Dense search** (ChromaDB, top-20) — semantic similarity
- **Sparse search** (BM25, top-20) — keyword matching
- **Reciprocal Rank Fusion** (k=60) — merges both ranked lists
- **Cross-encoder reranking** — keeps top-5 most relevant
- **Sufficiency check** — if insufficient, triggers web fallback with query reformulation (max 2 rounds)

### Step 3 — Evidence Consolidation (RAG: Augmentation)
Deduplicates evidence using fuzzy matching (thefuzz, ratio ≥ 80 on first 300 chars). If fewer than 3 unique chunks remain, runs a fallback search on the full claim. Sorts by relevance score.

### Step 4 — LLM Reasoning (RAG: Generation)
Sends top-10 evidence chunks to GPT-4o-mini. The LLM outputs:
- Overall verdict: `TRUE` / `FALSE` / `MISLEADING` / `NOT_ENOUGH_EVIDENCE`
- Confidence score (0.0–1.0)
- Reasoning (2-3 sentences)
- Per-sub-claim verdicts with supporting/contradicting source numbers
- List of relevant source numbers

**The LLM never sees or produces URLs.** It only references evidence by source number.

### Step 5 — Citation Building + Validation
Citations are built **programmatically** from the evidence chunks the LLM flagged as relevant. Each citation carries the real URL, source name, credibility score, and a text snippet — all from the actual evidence data, never from LLM output. This eliminates hallucinated URLs entirely. Citations are then deduplicated by URL.

### Step 6 — Feedback Loop (RAG: Self-Improvement)
If the verdict is confident enough (≥ 0.3), the verified claim and its evidence URLs are stored back into ChromaDB. Future queries about the same or similar topics will retrieve this as high-credibility KB evidence, enabling faster and more confident verdicts over time.

---

## Key Parameters Summary

| Component | Parameter | Value |
|-----------|-----------|-------|
| Embedding model | `text-embedding-3-small` | 1536 dimensions |
| Chunking | Size / overlap | 2000 / 250 chars |
| Vector DB | ChromaDB | Cosine similarity |
| Dense retrieval | Top-k | 20 |
| Sparse retrieval (BM25) | Top-k | 20 |
| RRF | k parameter | 60 |
| Cross-encoder reranker | Model | ms-marco-MiniLM-L-6-v2 |
| Reranker | Top-k kept | 5 |
| LLM (reasoning) | GPT-4o-mini | temp=0, max_tokens=1024 |
| LLM (extraction) | GPT-4o-mini | temp=0, max_tokens=512 |
| Evidence for LLM | Max chunks | 10 |
| Web search | Tavily | Max 5 results, 1h cache |
| Agentic loop | Max rounds | 2 |
| Fuzzy dedup | Threshold | ratio ≥ 80 |
| Feedback loop | Min confidence | 0.3 |
