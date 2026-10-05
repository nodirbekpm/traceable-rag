# Eval report 20261005-0419

## Retrieval

| mode | strategy | reranker | recall@5 | recall@10 | mrr | p50_ms | p95_ms |
|---|---|---|---|---|---|---|---|
| vector | fixed | none | 0.935 | 0.968 | 0.846 | 9.7 | 11.0 |
| text | fixed | none | 0.839 | 0.935 | 0.643 | 4.2 | 7.9 |
| hybrid | fixed | none | 0.952 | 0.984 | 0.847 | 22.7 | 30.1 |
| vector | sentence | none | 0.952 | 0.968 | 0.818 | 9.4 | 10.9 |
| text | sentence | none | 0.806 | 0.903 | 0.711 | 6.2 | 11.5 |
| hybrid | sentence | none | 0.968 | 0.984 | 0.864 | 21.9 | 29.2 |
| vector | section | none | 0.984 | 1.000 | 0.880 | 9.6 | 11.1 |
| text | section | none | 0.855 | 0.968 | 0.641 | 3.9 | 7.4 |
| hybrid | section | none | 0.984 | 1.000 | 0.907 | 21.9 | 26.5 |
| hybrid | section | cross-encoder | 1.000 | 1.000 | 0.951 | 1595.1 | 2122.1 |
