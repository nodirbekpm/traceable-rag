# Upwork portfolio entry

**Title (37 characters):**
Traceable RAG: every answer cited

**Description (~300 characters):**
Document AI that proves its answers. Values and citations link to exact spans in
SEC filings; anything not found in the source is rejected. Idempotent, versioned
extraction handles amended filings. A 72-question gold set measures accuracy,
citations and refusals. FastAPI, PostgreSQL + pgvector.

**Skills:** Python · FastAPI · PostgreSQL · pgvector · RAG · LLM evaluation · Docker

**Screenshots to attach (after the first full run):**
1. Viewer: answer with a citation highlighted in the filing
2. Viewer: fact history across an 8-K and its 8-K/A
3. `evals/reports/latest.md` rendered
4. `docs/perf/report.md` — HNSW vs IVFFlat table and an EXPLAIN plan
