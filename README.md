# Anchor

[![CI](https://github.com/nodirbekpm/traceable-rag/actions/workflows/ci.yml/badge.svg)](https://github.com/nodirbekpm/traceable-rag/actions/workflows/ci.yml)

**Traceable RAG over documents.** Every extracted value and every cited claim
points back to an exact character span in the source document — and anything
that cannot be traced is not shown.

Most document-AI systems treat model output as plain text. Anchor treats it as
evidence: it has a source, a version, a confidence and a measured accuracy.

| Guarantee | What it means in practice |
|---|---|
| **Provenance** | A value that cannot be located in the source is stored as `hallucinated`, never `verified`, and never reaches an answer. The database itself refuses a `verified` fact without a span. |
| **Versioning** | Nothing is deleted. A re-extraction or an amended filing (`8-K/A`) retires old values and links them to their replacement, so "what was this number six months ago, and why did it change?" always has an answer. |
| **Measurement** | Accuracy, citation correctness, refusal rate, latency and cost are numbers from a gold set — including the targets that were missed. |

Works on **any document you upload** — PDF, Word, HTML, text or Markdown — and ships with
SEC EDGAR `8-K` / `8-K/A` filings as a reproducible demo and evaluation corpus.

## Quick start

Requires Docker. Nothing else needs to be installed.

```bash
cp .env.example .env     # set EDGAR_USER_AGENT and GEMINI_API_KEY (free key)
docker compose up -d --build
```

Then fetch, extract, index and ask:

```bash
docker compose run --rm api python -m anchor.ingest --cik 320193 --limit 5   # Apple
docker compose run --rm api python -m anchor.extract
docker compose run --rm api python -m anchor.index
curl -N "localhost:8000/ask?q=Who+did+Apple+appoint+as+CEO"
```

Open **http://localhost:8000** for the viewer: the document on the left with
extracted values highlighted by status, answers on the right; clicking a value
or a citation scrolls to its exact span and shows model, versions and history.

Every command is idempotent: running it again downloads, extracts or embeds
nothing that is already there.

### Your own documents

Drop a file on the viewer (or `POST /documents`). Nothing runs yet: Anchor first
answers *what will this cost?* — pages, words, model calls, **seconds** and dollars,
estimated from this installation's own past runs. Confirm, and the analysis runs in
the background with a progress bar; long files are read in parts, and every value
still gets an exact span in the full document. Uploaded documents use a general
field set (dates, amounts, parties, people, percentages, deadlines, durations).

| Endpoint | Purpose |
|---|---|
| `POST /documents` | upload; returns the document and the estimate |
| `POST /documents/{id}/analyze` | start extraction and indexing in the background |
| `GET /documents/{id}/status` | progress: queued, extracting, indexing, ready, failed |
| `GET /ask?q=…&document_id=…` | ask, optionally limited to one document |

## Architecture

```
EDGAR API ──► fetcher ──► raw bytes (content-addressed, SHA-256) ──► source_document
                                   │
                       deterministic HTML → text (versioned)
                     ┌─────────────┴──────────────┐
                     ▼                            ▼
          extractor (LLM, JSON)             chunker ×3 strategies
          value + verbatim quote                  │
                     │                      local embeddings (CPU)
          validator: locate quote,                │
          normalize, range, confidence      pgvector HNSW + tsvector GIN
                     │                            │
     verified / needs_review / hallucinated       │
                     ▼                            ▼
             extracted_fact ◄── versioning ──► chunk
           (is_current, superseded_by)            │
                                                  ▼
                       question ─► hybrid retrieval (RRF) ─► rerank ─► LLM
                                                  │
                         per-claim citation check ─► SSE stream ─► viewer
                                                  │
                               Redis cache · query_log · eval harness
```

Stack: Python 3.12 · FastAPI · PostgreSQL 17 + pgvector · SQLAlchemy 2 + Alembic ·
Pydantic v2 · Redis · Gemini (any provider behind one interface) · fastembed
(ONNX, CPU) · Docker Compose · pytest · GitHub Actions.

## How provenance works

1. Raw HTML is converted to plain text by a deterministic, versioned function.
   Every span is a pair of character offsets into that text; raw bytes are kept
   unchanged, so the text can be rebuilt at any time.
2. The model returns each value with a **verbatim quote** that contains it. It
   is never asked for offsets — models miscount characters.
3. The validator finds the quote in the real text, then the value inside the
   quote. Found: the fact gets its span. Not found: `hallucinated`, no span.
4. Values are normalized (`$4.2M`, `4,200,000 USD`, `4.2 million dollars` →
   `4200000 USD`), range-checked, and sent to a review queue when confidence is low.

Each extraction run records model, provider build, prompt, schema and text
versions, tokens and list-price cost.

## How versioning works

- **Idempotency.** A document is extracted once per (model, prompt, schema, text
  version) — enforced by a partial unique index, not just by code.
- **Re-extraction.** A new version key creates a new run; its facts become
  current and the previous ones stay as history, each pointing at its replacement.
- **Amendments.** An `8-K/A` names the filing it amends by date. Anchor links
  the two (`supersedes_id`) and retires only the facts the amendment restates.
  An amendment fact that failed verification never displaces a verified one.
  Tested on a real pair: Apple's April 2026 CEO-transition 8-K and its September 8-K/A.
- **History.** `GET /facts/{id}/history` walks back through every earlier value.

## How answers are checked

1. Hybrid retrieval (vector + keyword, fused with reciprocal rank fusion) returns
   candidates; a local cross-encoder keeps the best six.
2. The model answers as one JSON line per claim: claim, source, verbatim quote.
3. Each line is checked the moment it completes: the quote must be in the cited
   chunk and every number in the claim must be in the quote. Passing claims are
   streamed immediately with document-level offsets; failing ones are dropped.
4. If nothing passes, the answer is "not found" — a measured behaviour, not an error.

## Evaluation

```bash
docker compose run --rm api python -m anchor.evals prepare   # separate eval database
docker compose run --rm api python -m anchor.evals run       # all three suites
```

The gold set lives in [`evals/golden`](evals/golden): **36 real filings** from
ten companies, **147 annotated fields**, **62 answerable and 10 unanswerable
questions**. Every gold quote is located in the source text, so provenance and
citations are scored by span overlap rather than string similarity.

| Suite | Metrics |
|---|---|
| Extraction | field accuracy, provenance correctness, wrong-value rate, hallucination rate, cost and time per document |
| Retrieval | recall@5, recall@10, MRR for vector / keyword / hybrid × three chunking strategies, plus reranking |
| Answers | answer accuracy, citation correctness, refusal rate on unanswerable questions, false refusals, TTFT, cost |

Every run is stored in `eval_result` with per-question details, so a regression
can be traced to the questions that changed. The latest report is written to
[`evals/reports/latest.md`](evals/reports).

> **Results:** pending the first full run against a live model. This section is
> filled from `evals/reports/latest.md`; until then no accuracy number is claimed.

## Measurements

Intel i5-12400 (6 cores), no GPU, everything in Docker. Targets that were missed
are listed as missed.

| What | Target | Measured | Status |
|---|---|---|---|
| Embedding throughput, `bge-small-en-v1.5`, ~740-char chunks | > 200 chunks/s | 21–25 chunks/s | **missed** (CPU only; [decision 003](docs/decisions/003-local-cpu-embeddings.md)) |
| Embedding throughput, `all-MiniLM-L6-v2` | > 200 chunks/s | 44–52 chunks/s | **missed** |
| Re-indexing an indexed corpus | no work | 0 chunks embedded, 0.1 s | ok |
| Re-ingesting stored filings | no work | 0 downloads, 0 rows | ok |
| Retrieval p95 (rerank excluded) | < 150 ms | pending `python -m anchor.bench` | — |
| Time to first claim | < 1.5 s | pending first live run | — |
| Cache hit | < 50 ms | pending | — |

`python -m anchor.bench` measures retrieval latency per mode, saves
`EXPLAIN (ANALYZE, BUFFERS)` plans, compares HNSW and IVFFlat (build time, size,
recall@10, p50/p95 against an exact scan) and reports what the partial index on
current facts saves. Output: [`docs/perf/report.md`](docs/perf).

## Engineering decisions

Each block: problem → measurement → alternatives → choice → result.
Full records in [`docs/decisions`](docs/decisions).

**Quotes instead of offsets.** *Problem:* the spec asked the model for
character spans; models miscount, which would reject correct values. *Alternatives:*
ask for offsets; ask for line numbers; ask for a verbatim quote and locate it in
code. *Choice:* quote + deterministic lookup with whitespace/quote-style
tolerance (confidence × 0.9 when tolerance is needed). *Result:* the span is a
check, not a claim; scored by the extraction suite.

**Local CPU embeddings.** *Problem:* the spec assumed 1536-d paid embeddings and
> 200 chunks/s; the project must run free and the machine has no CUDA.
*Measurement:* bge-small 21–25 chunks/s, MiniLM 44–52 chunks/s.
*Alternatives:* paid API; free-tier API with daily limits; local ONNX.
*Choice:* local bge-small (384-d), model name stored per chunk. *Result:* target
missed and recorded; 1,000 chunks ≈ 45 s, once.

**PostgreSQL full-text before Elasticsearch.** *Problem:* pure vector search
misses exact tokens (`Item 2.02`, `$4.2M`). *Alternatives:* Elasticsearch/OpenSearch;
`tsvector` + GIN in the same database. *Choice:* `tsvector` with any-word
matching, fused with vector results by RRF — no score calibration, no second
datastore. *Result:* compared against vector-only and keyword-only in the
retrieval suite; Elasticsearch enters only if `tsvector` recall is measurably short.

**Estimate before work.** *Problem:* an uploaded 100-page PDF can take minutes and
real money, and a user who cannot see that will abandon it. *Choice:* uploads are
stored and measured first; time comes from this installation's history (seconds
per 1k input tokens of past runs), embedding rate and the provider's rate limit.
*Result:* the user decides with numbers; accuracy of the estimate is tracked in
[decision 004](docs/decisions/004-any-document.md).

**Verification before streaming.** *Problem:* streaming raw tokens shows claims
before they are checked. *Choice:* NDJSON, one claim per line, verified when the
line completes. *Result:* the user waits for one claim, not the whole answer,
and never sees an unverified number.

## Data model

| Table | Purpose |
|---|---|
| `source_document` | raw filing or exhibit: URL, accession, SHA-256, path to unchanged bytes, `supersedes_id`, `parent_id` |
| `extraction_run` | one model call: model, build, prompt/schema/text version, tokens, cost, status |
| `extracted_fact` | value, normalized value, unit, span, excerpt, confidence, status, `is_current`, `superseded_by` |
| `review_queue` | low-confidence facts awaiting a human decision |
| `chunk` | exact slice of the text, strategy, section, `vector(384)`, generated `tsvector` |
| `query_log` | question, retrieved chunks, answer, citations, per-stage latency, cost, cache hit |
| `eval_result` | suite, configuration, metrics, per-item details |

## Development

```bash
uv sync
docker compose up -d db redis
uv run alembic upgrade head
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
```

Tests run against a real PostgreSQL in a scratch database and never touch the
network: EDGAR, the language model and the embedder are replaced by fakes.

## License

[MIT](LICENSE)
