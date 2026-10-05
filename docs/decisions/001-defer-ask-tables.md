# 001. Retrieval-side tables are added by the stage that needs them

Date: 2026-10-02 · Status: accepted

## Problem

The original data model listed seven tables up front and fixed `chunk.embedding` as
`vector(1536)` — the size of a paid OpenAI embedding. The project has to run on free
tooling, and the reference machine has no CUDA GPU; local CPU models produce 384 or
768 dimensions. Fixing the size before measuring would force a type-changing
migration later.

## Options

- Create all seven tables now with `vector(1536)` — re-migrate if the model changes.
- Declare `vector` without a size — HNSW cannot index a column of unknown dimension.
- Create the core tables now; add `chunk`, `query_log` and `eval_result` with the
  stage that uses them.

## Decision

Stage 1 creates `source_document`, `extraction_run`, `extracted_fact` and
`review_queue`, and enables the `vector` extension. `chunk` arrives with indexing,
`query_log` with answers, `eval_result` with the eval harness.
`source_document` also gets `external_id` (EDGAR accession number, unique) and
`publisher_id` (CIK), so duplicates are detected before downloading.

## Result

No performance effect — this is an ordering decision. The provenance constraint
(no `verified` fact without a span) and the partial index on current facts were in
the first migration.
