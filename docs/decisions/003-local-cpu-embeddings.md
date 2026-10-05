# 003. Local CPU embeddings, 384 dimensions — throughput target missed

Date: 2026-10-02 · Status: accepted (to be revisited against recall@5)

## Problem

The plan assumed `vector(1536)` embeddings and more than 200 chunks per second. The
project must run on free tooling; the reference machine has no CUDA GPU (AMD RX 570)
and everything runs in Docker.

## Measurement

Intel i5-12400 (12 threads), Docker, average chunk ≈ 740 characters.

| Model | Dimensions | batch=4 | batch=32 |
|---|---|---|---|
| BAAI/bge-small-en-v1.5 | 384 | 25 chunks/s | 21 chunks/s |
| sentence-transformers/all-MiniLM-L6-v2 | 384 | 44 chunks/s | 52 chunks/s |

First real indexing run (5 filings, 3 strategies, 95 chunks, including model load):
8.5 s. Free host memory was about 2 GB during the measurement, so these numbers may
be on the low side.

## Options

- Paid embedding API (1536 dimensions).
- Free-tier embedding API — daily limits, network-bound, needs a key.
- Local ONNX model on CPU through fastembed — free, no key, slower.

## Decision

`BAAI/bge-small-en-v1.5` through fastembed, `chunk.embedding = vector(384)`. The
model name is a setting and is stored on every chunk; a model with another size needs
a migration, and indexing refuses to run with a clear error until it exists. MiniLM is
twice as fast but not trained for retrieval; recall@5 in the eval suite, not speed,
decides between them.

## Result

- **Target missed:** 21–25 chunks/s against > 200. Cause: no GPU.
- Practical impact is small: 1,000 chunks take about 45 s, once, and re-indexing is
  idempotent.
