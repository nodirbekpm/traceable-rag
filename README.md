# Anchor

[![CI](https://github.com/nodirbekpm/traceable-rag/actions/workflows/ci.yml/badge.svg)](https://github.com/nodirbekpm/traceable-rag/actions/workflows/ci.yml)

Traceable RAG over documents: every extracted value and every cited claim points
back to an exact character span in the source document.

Three guarantees:

1. **Provenance** — a value that cannot be located in the source text is never
   stored as `verified` and never reaches an answer.
2. **Versioning** — results are never deleted. A re-extraction or an amended
   filing (`8-K/A`) supersedes the old record and keeps the history.
3. **Measurement** — accuracy, citation correctness, latency and cost are
   reported as numbers, including the targets that were missed.

Demo domain: SEC EDGAR `8-K` and `8-K/A` filings.

## Quick start

Requires Docker. Nothing else needs to be installed.

```bash
cp .env.example .env        # set EDGAR_USER_AGENT="Your Name you@example.com"
docker compose up -d --build
curl localhost:8000/health  # {"status":"ok","database":"ok",...}
```

`docker compose up` starts PostgreSQL (pgvector), Redis and the API, and applies
database migrations before the API accepts requests.

Fetch the five most recent 8-K / 8-K/A filings of a company by CIK:

```bash
docker compose run --rm api python -m anchor.ingest --cik 320193 --limit 5
```

Running the same command again downloads nothing and adds no rows.

## What works today

| Area | State |
|---|---|
| EDGAR fetcher | Lists and downloads `8-K` / `8-K/A`; contact User-Agent enforced, requests spaced under SEC's 10 req/s limit, retries on 429/5xx |
| Raw storage | Bytes stored exactly as received, addressed by SHA-256 |
| Idempotent ingest | A filing is skipped by accession number before download, and by content hash after |
| Data model | `source_document`, `extraction_run`, `extracted_fact`, `review_queue` |
| Extraction, retrieval, answers, evals | Not built yet |

## Data model

Two guarantees are enforced by the database, not only by application code:

- `ck_extracted_fact_verified_requires_span` — a fact cannot have
  `validation_status = 'verified'` unless `span_start`, `span_end` and
  `source_excerpt` are all present.
- `ix_extracted_fact_current` — partial index `WHERE is_current`; superseded
  rows are kept forever but stay out of the index that serves current reads.

`source_document.supersedes_id` links an amendment to the filing it replaces.

## Development

```bash
uv sync
docker compose up -d db redis
uv run alembic upgrade head
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
```

Tests run against a real PostgreSQL in a scratch database (`<name>_test`) and
never touch the network: EDGAR is replaced by an in-memory transport.

Design decisions that deviate from the original spec are recorded in
[docs/decisions](docs/decisions).

## License

[MIT](LICENSE)
