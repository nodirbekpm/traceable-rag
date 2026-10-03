# Case study: making LLM output auditable

**Anchor** — traceable RAG over SEC filings. Repository: github.com/nodirbekpm/traceable-rag

## The problem

Teams that extract numbers from documents with an LLM usually have a prototype
in a week and four unanswerable questions in production. Which sentence did
this dashboard number come from? The document was processed twice — which row
is right? The company corrected its filing — what happened to the old value?
The model was upgraded — is the new one actually more accurate?

RAG systems share the root cause. An answer can quote a wrong figure in a
confident tone and nobody notices, because model output is accepted as text
rather than checked as evidence.

## What I built

Anchor treats every model output as a claim that must be proven against the
source.

- **Provenance by construction.** The model returns each value with a verbatim
  quote. Code — not the model — finds that quote in the document and records
  the exact character span. If the quote is not there, the value is stored as
  a hallucination and never shown. A database constraint makes it impossible to
  mark a value verified without a span.
- **Versioning without deletion.** Extraction is idempotent per model, prompt,
  schema and text version. A newer run, or an amended filing (8-K/A), retires
  old values and links them to their replacements, so the history of any
  number can be walked back. This runs on a real amendment pair from Apple's
  2026 CEO transition.
- **Answers that cite or refuse.** Hybrid retrieval (pgvector + PostgreSQL
  full-text, fused with reciprocal rank fusion) feeds a model that must answer
  one claim per line, each with a quote. Every line is verified the moment it
  completes and only then streamed; unsupported claims are dropped. If nothing
  survives, the answer is "not found".
- **Measurement.** A gold set of 36 real filings, 147 annotated fields and 72
  questions (10 deliberately unanswerable) scores field accuracy, provenance
  correctness, hallucination rate, recall@k across three chunking strategies and
  three retrieval modes, answer accuracy, citation correctness and refusal rate.
  Every run is stored, so regressions are visible.

## Results

<!-- Filled from evals/reports/latest.md and docs/perf/report.md after the first full run. -->
Pending the first full run against a live model. Measured so far: re-ingesting
and re-indexing do zero work; embedding throughput on a CPU-only machine is
21–25 chunks/s against a 200 chunks/s target — recorded as missed, with the
reasoning, rather than hidden.

## Engineering choices

Everything runs on free tooling in one `docker compose up`: PostgreSQL does
vectors, full-text search and versioned storage; embeddings run locally on CPU;
the language model sits behind a one-method interface. New technology enters
only after a measured bottleneck — the README records each decision as problem,
measurement, alternatives, choice and result.

## What a client gets

A pipeline where every number on a dashboard can be clicked back to its
sentence, re-processing never creates duplicates, corrections keep their
history, and "how accurate is it?" has an answer in numbers.
