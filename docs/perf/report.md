# Performance report

Hardware: see README. All numbers are wall-clock from the application side.

## Retrieval latency on the eval corpus (k=10, warm)

| mode | p50_ms | p95_ms | queries |
|---|---|---|---|
| vector | 13.7 | 18.4 | 72 |
| text | 6.4 | 12.7 | 72 |
| hybrid | 27.3 | 33.7 | 72 |

Query plans: [vector](explain-vector.txt), [text](explain-text.txt).

## Partial index on current facts

```json
{
  "facts": 289,
  "current": 280,
  "partial_kb": 16.0,
  "full_kb": 16.0
}
```

## Vector index study (50,000 384-d vectors, 100 queries)

Data: 910 real chunk embeddings, each repeated with noise ±0.02. Recall is measured against an exact scan of the same table.

| index | setting | build_s | size_mb | recall@10 | p50_ms | p95_ms |
|---|---|---|---|---|---|---|
| none (exact scan) | — | — | — | 1.0 | 14.2 | 22.9 |
| hnsw m=16 ef_construction=64 | hnsw.ef_search=40 | 13.38 | 96.0 | 0.958 | 0.6 | 1.4 |
| hnsw m=16 ef_construction=64 | hnsw.ef_search=100 | 13.38 | 96.0 | 0.973 | 0.6 | 1.4 |
| hnsw m=32 ef_construction=128 | hnsw.ef_search=40 | 32.31 | 99.3 | 0.989 | 0.6 | 1.1 |
| hnsw m=32 ef_construction=128 | hnsw.ef_search=100 | 32.31 | 99.3 | 1.0 | 0.7 | 1.4 |
| ivfflat lists=223 | ivfflat.probes=1 | 6.61 | 77.9 | 0.979 | 0.4 | 0.8 |
| ivfflat lists=223 | ivfflat.probes=10 | 6.61 | 77.9 | 1.0 | 1.3 | 2.8 |
