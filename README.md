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

Extract facts from the ingested filings (needs `GEMINI_API_KEY` in `.env`; the
free tier is enough):

```bash
docker compose run --rm api python -m anchor.extract --limit 5
```

Chunk and embed the filings for retrieval (no API key; the model is downloaded
once, about 130 MB, and runs on CPU):

```bash
docker compose run --rm api python -m anchor.index
```

## How provenance works

1. The raw HTML is converted to plain text by a deterministic, versioned
   function. Every span is a pair of character offsets into that text.
2. The model returns each value together with a **verbatim quote** that contains
   it. It is never asked for offsets — models miscount characters.
3. The validator looks the quote up in the real text, then the value inside the
   quote. Found: the fact gets its span and can become `verified`. Not found:
   it is stored as `hallucinated`, without a span, and is never shown as an answer.
4. Values are normalized (`$4.2M`, `4,200,000 USD`, `4.2 million dollars` →
   `4200000 USD`), range-checked, and sent to review when confidence is low.

Each run records model, model build, prompt version, schema version, text
version, tokens and list-price cost.

## How versioning works

- **Re-extraction.** Changing the model, prompt, schema or text conversion
  creates a new run. Its facts become current; the previous run's facts stay
  in the table as history, each pointing at its replacement.
- **Amendments.** An `8-K/A` names the filing it amends by date. Anchor links
  the two (`supersedes_id`) and retires only the facts the amendment restates.
  An amendment fact that failed verification never displaces a verified one.
- **History.** `GET /facts/{id}/history` returns a value followed by every
  earlier value it replaced, across runs and across filings.

## How answers are checked

Ask a question and watch the answer arrive claim by claim:

```bash
curl -N "localhost:8000/ask?q=Who+was+appointed+Chief+Financial+Officer"
```

1. Retrieval returns candidate chunks (hybrid by default), a reranker keeps the best six.
2. The model must answer as one JSON line per claim: the claim, the source it
   relies on and a verbatim quote.
3. Each line is checked when it completes: the quote must be in the cited chunk
   and every number in the claim must be in the quote. Passing claims are sent
   immediately with document-level offsets; failing ones are dropped and counted.
4. If no claim passes, the answer is "not found" — a measured behaviour, not an error.

## What works today

| Area | State |
|---|---|
| EDGAR fetcher | Lists and downloads `8-K` / `8-K/A`; contact User-Agent enforced, requests spaced under SEC's 10 req/s limit, retries on 429/5xx |
| Raw storage | Bytes stored exactly as received, addressed by SHA-256 |
| Idempotent ingest | A filing is skipped by accession number before download, and by content hash after |
| Data model | `source_document`, `extraction_run`, `extracted_fact`, `review_queue` |
| Extraction | 14 fields from 8-K filings via an LLM (Gemini by default, provider is a setting); every value verified against the source text |
| Validation | Normalization for money, per-share, percent, date and Item values; range checks; `verified` / `needs_review` / `rejected` / `hallucinated` |
| Idempotency | A document is extracted once per (model, prompt, schema, text version); enforced by a partial unique index |
| Versioning | A newer run or an amending `8-K/A` retires old facts (`is_current = false`, `superseded_by`); nothing is deleted |
| Review queue | Low-confidence facts wait for a human decision |
| API | `/documents`, `/documents/{id}/facts`, `/facts/{id}/history`, `/review`, `/review/{id}/resolve` |
| Chunking | Three strategies stored side by side: fixed window, sentence window, section-aware (`Item` boundaries); every chunk is an exact slice of the source text |
| Embedding and indexes | Local CPU model (`BAAI/bge-small-en-v1.5`, 384 dims), pgvector HNSW index, `tsvector` + GIN index |
| Retrieval | Vector (HNSW), keyword (`tsvector`) and hybrid (reciprocal rank fusion) behind one interface |
| Reranking | Local cross-encoder (`ms-marco-MiniLM-L-6-v2`) or LLM grading, switchable per request |
| Answers | `GET /ask` streams server-sent events; every claim carries a verified citation with document offsets; unsupported claims are dropped; "not found" when nothing survives |
| Cache and logging | Redis answer cache keyed by question, configuration and corpus version; `query_log` with per-stage latency and cost |
| Evals | Not built yet |

## Data model

Two guarantees are enforced by the database, not only by application code:

- `ck_extracted_fact_verified_requires_span` — a fact cannot have
  `validation_status = 'verified'` unless `span_start`, `span_end` and
  `source_excerpt` are all present.
- `ix_extracted_fact_current` — partial index `WHERE is_current`; superseded
  rows are kept forever but stay out of the index that serves current reads.

`source_document.supersedes_id` links an amendment to the filing it replaces.

## Measurements

Numbers are from an Intel i5-12400 (6 cores), no GPU, everything in Docker.
Targets that were missed are listed as missed.

| What | Target | Measured | Status |
|---|---|---|---|
| Embedding throughput, `bge-small-en-v1.5`, ~740-char chunks | > 200 chunks/s | 21-25 chunks/s | **missed** (CPU only; see [decision 003](docs/decisions/003-local-cpu-embeddings.md)) |
| Embedding throughput, `all-MiniLM-L6-v2` | > 200 chunks/s | 44-52 chunks/s | **missed** |
| Re-indexing an already indexed corpus | no work | 0 chunks embedded, 0.1 s | ok |
| Re-ingesting already stored filings | no work | 0 downloads, 0 rows | ok |

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
