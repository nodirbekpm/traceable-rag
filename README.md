# Anchor

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

## Status

Under construction. See [CHANGELOG.md](CHANGELOG.md).

## License

[MIT](LICENSE)
