# 005. Versions of uploaded documents, and deleting uploads

Date: 2026-10-05 · Status: accepted

## Problem

A user needs to upload an edited file as a new version and to delete their own
uploads. Versions are the versioning guarantee itself. Deletion looks like it
contradicts "old results are never deleted".

## Options

- No deletion, archive only — visitors who upload to a public demo cannot remove
  their files.
- Soft delete (flag, data kept) — misleads a user who was told the file is gone.
- Full deletion for uploads only (every version, fact, run, chunk and the stored
  file); filings cannot be deleted.

## Decision

- **Versions.** `POST /documents/{id}/versions` creates a new `source_document` with
  `supersedes_id` pointing at the previous one. Once analysed, *every* current fact of
  the previous version becomes history (unlike an 8-K/A, which only replaces what it
  restates). Restated facts point at their successor.
- **Pairing.** First by (field, label), then by same field and same normalized value.
  In a live run the model labelled one value differently between runs ("initial term
  start" / "initial term beginning date"), and three real changes were buried in
  twelve false removed/added pairs.
- **Deletion.** A user owns the files they upload. The no-deletion rule protects
  results the system derives from a source; it does not override the user's right to
  remove their own file. Only `doc_type = upload`; filings return 403.

## Result (live model, sample contract)

| Comparison | Before the pairing fix | After |
|---|---|---|
| v1 → v2 (3 real changes) | 3 changed + 12 false removed/added | — (v2 was linked under the old rule) |
| v2 → v3 (2 real changes) | — | 2 changed, 0 false |
