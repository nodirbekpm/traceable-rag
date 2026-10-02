# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
