# TripCraft — AI Travel Planning & Booking Agent

An AI-powered travel planner that researches, plans, verifies, and books trips through a conversational interface with real-time progress streaming.

## Architecture

- **Backend**: FastAPI + LangGraph + LangChain (Python 3.11+)
- **Frontend**: Vite + React 18 + TypeScript + Tailwind CSS v4
- **Database**: SQLite (async via aiosqlite)
- **LLM**: GPT-4o (reasoning) + GPT-4o-mini (narration)
- **Streaming**: Server-Sent Events (SSE)

## Agent Pipeline

```
User Chat → Intent Parser → Research → Checkpoint 1 → Planner → Optimizer → Checkpoint 2 → Verifier → Checkpoint 3 → Finalize
```

**6 Core Agents**:
1. **Intent Parser** — Heuristic-first parsing (regex, keywords) with LLM fallback
2. **Research Agent** — LLM query generation + parallel API calls (flights, hotels, activities, weather, advisories)
3. **Planner** — Heuristic scheduling + LLM narration for day-by-day descriptions
4. **Budget Optimizer** — Pure greedy algorithm, no LLM
5. **Verification Agent** — Cross-references all places against Google Places API
6. **Coordinator** — Checkpoint management, price re-validation, orchestration

**Stretch Agents**: Re-planner (LLM change interpretation), Local Tips (web search + LLM summarization)

## Quick Start

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # Fill in your API keys
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

### Environment Variables

Copy `backend/.env.example` and fill in:

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | OpenAI API key for GPT-4o / GPT-4o-mini |
| `SERPAPI_API_KEY` | Yes | SerpAPI for flight/hotel/activity search |
| `GOOGLE_MAPS_API_KEY` | Yes | Google Maps + Places API |
| `AMADEUS_CLIENT_ID` | No | Amadeus flight fallback |
| `AMADEUS_CLIENT_SECRET` | No | Amadeus flight fallback |
| `OPENWEATHER_API_KEY` | No | Weather forecasts |
| `EXCHANGERATE_API_KEY` | No | Currency conversion |

## Key Design Decisions

- **Heuristics-first**: LLM only for narrative generation, query generation, and ambiguity resolution. All parsing, scheduling, optimization, and verification are deterministic.
- **Tiered LLM**: GPT-4o for complex reasoning (intent, re-planning), GPT-4o-mini for narration (~60-70% cost reduction)
- **Progressive SSE**: Stream each research sub-result as it completes — frontend renders partial data immediately
- **Anti-hallucination**: Planner constrained to research data only + Verification Agent cross-references all places against Google Places
- **Caching + fallbacks**: TTLCache (1hr TTL) + API fallback chains (SerpAPI → Amadeus, etc.)
- **Pre-baked demos**: 3 sample trips in DB for reliable demos even when APIs are down

## Project Structure

```
week2/
├── backend/
│   ├── main.py                  # FastAPI app
│   ├── app/
│   │   ├── config.py            # Settings
│   │   ├── models/              # Pydantic models
│   │   ├── agents/              # LangGraph agents
│   │   ├── tools/               # API wrappers
│   │   ├── services/            # Business logic
│   │   ├── db/                  # SQLite + ORM
│   │   └── api/                 # FastAPI routes
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── pages/               # HomePage, TripPage
│   │   ├── components/          # Chat, Itinerary, Budget, Map, etc.
│   │   ├── hooks/               # useSSE, useTrip
│   │   ├── services/            # API client
│   │   └── types/               # TypeScript types
│   └── package.json
├── PLAN.md                      # Detailed architecture plan
└── README.md
```
