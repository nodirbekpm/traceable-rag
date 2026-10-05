# 002. The model returns a verbatim quote, not character offsets

Date: 2026-10-02 · Status: accepted

## Problem

The requirement was that the model returns a source span with every value. Language
models are unreliable at counting characters: asking them for `span_start` /
`span_end` produces wrong offsets and would reject correct values. A second question
was what the offsets refer to — the raw file is HTML, whose character positions do
not match the text a reader sees.

## Options

- Ask the model for offsets — miscounting.
- Number the lines and ask for a line number — spans become coarse (whole lines).
- Ask for a verbatim quote and compute the offsets in code.

## Decision

- The model returns `value` plus a `quote` that contains it. `provenance.locate`
  finds the quote in the real text: exact match first, then a match tolerant of
  whitespace and quote/dash styles (confidence × 0.9 when tolerance was needed).
- If the quote is not found, or the value is not inside it, the fact is stored as
  `hallucinated`, without a span.
- `span_start` / `span_end` point at the value itself; `source_excerpt` holds the quote.
- Offsets refer to the output of a deterministic, versioned text conversion
  (`TEXT_VERSION`) recorded on every run. Raw bytes are stored unchanged, so the text
  can be rebuilt at any time.

## Result

The span is a check performed by code, not a claim made by the model. Accuracy and
provenance correctness are scored by the extraction eval suite.
