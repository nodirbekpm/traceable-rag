# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Deterministic, versioned HTML to text conversion that span offsets refer to.
- Extraction schema for 8-K filings (14 fields) and value normalization for
  money, per-share, percent, date and Item values.
- Provenance validator: values are located in the source text through a verbatim
  quote; anything not found is stored as `hallucinated` and never `verified`.
- Provider-neutral LLM client with a Gemini backend; runs record model build,
  prompt, schema and text versions, tokens and list-price cost.
- `python -m anchor.extract` command.
- Idempotent extraction keyed by document, model, prompt, schema and text version.
- Fact supersession across runs and across amended filings, with full history.
- Automatic linking of an `8-K/A` to the `8-K` it amends.
- Review queue for low-confidence facts.
- Read API for documents, facts, fact history and the review queue.
- Three chunking strategies (fixed, sentence window, section-aware) whose chunks
  are exact slices of the source text.
- Local CPU embeddings (`BAAI/bge-small-en-v1.5`) and the `chunk` table with
  HNSW and GIN indexes; `python -m anchor.index` command.
- Exhibit 99 press releases are ingested with their filing (`parent_id`).
- Vector, keyword and hybrid retrieval; cross-encoder and LLM rerankers.
- Streaming `GET /ask` endpoint with per-claim citation verification and
  "not found" answers; Redis answer cache; `query_log` table.
- Eval harness (`python -m anchor.evals`): gold set of 36 filings, 147 fields,
  72 questions; extraction, retrieval and answer suites; `eval_result` history.
- Viewer page at `/`: highlighted spans, streaming answers, provenance and history.
- `python -m anchor.bench`: retrieval latency, EXPLAIN plans, HNSW vs IVFFlat,
  partial-index saving; `HNSW_EF_SEARCH` setting.
- Case study and portfolio entry drafts in `docs/`.
- Upload any document (PDF, DOCX, HTML, TXT, MD); time and cost estimate before
  analysis; background analysis with progress; general field set for uploads;
  long documents read in parts; questions scoped to one document.
- Redesigned viewer: three-step guide, drag-and-drop upload, legend, plain-language stats.
- Gemini calls retry on rate limits; per-share amounts with a "per share" suffix normalize.
- New versions of uploaded documents with a what-changed view; deletion of uploads.

## [0.1.0] - 2026-10-02

### Added

- Docker Compose stack: PostgreSQL 17 with pgvector, Redis, FastAPI service with
  a `/health` endpoint; migrations are applied before the API starts.
- CI on every pull request: `ruff check`, `ruff format --check`, `pytest`
  against a PostgreSQL service container.
- Core data model and first migration: `source_document`, `extraction_run`,
  `extracted_fact`, `review_queue`.
- Database-level provenance rule: a fact cannot be `verified` without a source span.
- Partial index over current facts (`WHERE is_current`).
- EDGAR client for `8-K` / `8-K/A` filings with a mandatory contact User-Agent,
  request spacing and retries on 429/5xx.
- Content-addressed raw document storage keyed by SHA-256.
- Idempotent ingest command: `python -m anchor.ingest --cik <CIK> --limit <N>`.

[Unreleased]: https://github.com/nodirbekpm/traceable-rag/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/nodirbekpm/traceable-rag/releases/tag/v0.1.0
