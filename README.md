# ai-league-chaos-is-a-ladder

**AI League Hackathon -- Team Chaos is a Ladder**

## Week 1: Real-Time News Claim Verification System (RAG / Agentic RAG)

A 6-step backend pipeline that verifies news claims using Agentic RAG:

1. **Claim Extraction + Decomposition** -- isolate verifiable facts from raw text
2. **Evidence Retrieval** -- hybrid search (dense + BM25 + RRF), cross-encoder reranking, web fallback with query reformulation
3. **Evidence Consolidation** -- deduplicate, filter, prepare augmented context
4. **LLM Reasoning** -- GPT-4o-mini generates a grounded verdict from retrieved evidence
5. **Citation Validation** -- fuzzy-match citations to real evidence, strip hallucinations
6. **Feedback Loop** -- store verified claims back into ChromaDB for self-improvement

See [week1/README.md](week1/README.md) for setup instructions, API docs, and full details.