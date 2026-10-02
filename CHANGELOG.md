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
