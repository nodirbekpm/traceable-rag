# 004. Analyse any uploaded document, not only EDGAR filings

Date: 2026-10-03 · Status: accepted

## Problem

The original scope limited the demo domain to SEC EDGAR. In live testing it became
clear that a visitor wants to try their own document; a system that only reads one
public source looks like a demo, not a service.

## Options

- EDGAR only, any company by CIK — a visitor still cannot try their own file.
- Upload and analyse immediately — a large file brings unexpected time and cost, and
  the user cannot see what is happening.
- Upload → estimate (time, cost) → confirmation → background analysis with progress.

## Decision

The third option. Conversion (`text.document_to_text`) depends on the format: HTML,
PDF (pypdf), DOCX (python-docx), TXT/MD. All spans refer to this output; raw bytes
stay unchanged. Uploads use a general field profile (`g1`); filings keep the 8-K
profile (`s1`). The 8-K prompt was verified to render byte-for-byte as before (same
SHA-256), so existing runs and the idempotency key remain valid. Long documents are
read in 40,000-character windows; quotes are located in the full text.

The estimate uses this installation's history: seconds per 1,000 input tokens of
finished runs (a default of 3 s until there are three runs), the measured embedding
rate (20 chunks/s) and the free-tier rate limit.

## Result

- Provenance, versioning and measurement are unchanged: quote checking is
  format-independent, identical content is never stored twice, and the estimate comes
  from real history.
- The eval corpus stays EDGAR, so results remain reproducible.
- First live check: estimate 6 s, actual analysis 5.3 s (one-page contract).
