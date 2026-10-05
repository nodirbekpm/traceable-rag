"""Database performance study: `python -m anchor.bench`.

1. Retrieval latency per mode on the eval corpus, with EXPLAIN (ANALYZE, BUFFERS).
2. HNSW vs IVFFlat on a synthetic table: build time, size, recall@10, p50/p95.
3. What the partial index on current facts saves compared with a full index.

Writes docs/perf/report.md and the raw query plans next to it. Runs against the
eval database (see `python -m anchor.evals prepare`).
"""

import argparse
import json
import logging
import random
import time
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from anchor.config import get_settings
from anchor.evals.metrics import percentile

logger = logging.getLogger("anchor.bench")
OUT = Path("docs/perf")
DIMENSIONS = 384

_COSINE = "(embedding vector_cosine_ops)"
INDEX_VARIANTS = [
    (
        "hnsw m=16 ef_construction=64",
        f"hnsw {_COSINE} WITH (m = 16, ef_construction = 64)",
        [("hnsw.ef_search", 40), ("hnsw.ef_search", 100)],
    ),
    (
        "hnsw m=32 ef_construction=128",
        f"hnsw {_COSINE} WITH (m = 32, ef_construction = 128)",
        [("hnsw.ef_search", 40), ("hnsw.ef_search", 100)],
    ),
    (
        "ivfflat lists={lists}",
        f"ivfflat {_COSINE} WITH (lists = {{lists}})",
        [("ivfflat.probes", 1), ("ivfflat.probes", 10)],
    ),
]


def _timed(session: Session, sql: str, params: dict, runs: int = 1) -> tuple[list, float]:
    started = time.perf_counter()
    for _ in range(runs):
        rows = session.execute(text(sql), params).all()
    return rows, (time.perf_counter() - started) * 1000 / runs


def retrieval_latency(session: Session) -> tuple[list[dict], dict[str, str]]:
    from anchor.embedding import build_embedder
    from anchor.evals.suites import load
    from anchor.retrieval import MODES, retrieve

    embedder = build_embedder(get_settings())
    questions = [q["question"] for q in load("questions.jsonl")]
    rows = []
    for mode in MODES:
        retrieve(session, embedder, questions[0], mode=mode)  # warm caches
        samples = []
        for question in questions:
            started = time.perf_counter()
            retrieve(session, embedder, question, mode=mode, k=10)
            samples.append((time.perf_counter() - started) * 1000)
        rows.append(
            {
                "mode": mode,
                "p50_ms": percentile(samples, 50),
                "p95_ms": percentile(samples, 95),
                "queries": len(samples),
            }
        )

    vector = embedder.embed_query(questions[0])
    plans = {}
    explain = "EXPLAIN (ANALYZE, BUFFERS, COSTS OFF) "
    plans["vector"] = (
        "SELECT id FROM chunk WHERE chunk_strategy = 'section' "
        "ORDER BY embedding <=> CAST(:v AS vector) LIMIT 10",
        {"v": str(vector)},
    )
    # Same expression as retrieval.keyword_query, written out so EXPLAIN can bind it.
    tsquery = "replace(plainto_tsquery('english', :q)::text, '&', '|')::tsquery"
    plans["text"] = (
        f"SELECT id FROM chunk WHERE chunk_strategy = 'section' AND tsv @@ {tsquery} "
        f"ORDER BY ts_rank_cd(tsv, {tsquery}) DESC LIMIT 10",
        {"q": questions[0]},
    )
    rendered = {}
    for name, (sql, params) in plans.items():
        rendered[name] = "\n".join(
            row[0] for row in session.execute(text(explain + sql), params).all()
        )
    return rows, rendered


def index_study(session: Session, n: int, queries: int) -> list[dict]:
    session.execute(text("DROP TABLE IF EXISTS bench_vectors"))
    session.execute(
        text(f"CREATE TABLE bench_vectors (id serial PRIMARY KEY, embedding vector({DIMENSIONS}))")
    )
    # `WHERE g > 0` ties the inner query to the row, so every row gets its own random vector.
    session.execute(
        text(
            "INSERT INTO bench_vectors (embedding) "
            f"SELECT (SELECT array_agg(random() - 0.5) FROM generate_series(1, {DIMENSIONS}) "
            "        WHERE g > 0)::vector FROM generate_series(1, :n) AS g"
        ),
        {"n": n},
    )
    session.commit()
    rng = random.Random(7)
    probes = [str([rng.random() - 0.5 for _ in range(DIMENSIONS)]) for _ in range(queries)]
    knn = "SELECT id FROM bench_vectors ORDER BY embedding <=> CAST(:v AS vector) LIMIT 10"

    session.execute(text("SET enable_indexscan = off"))
    exact = [{row[0] for row in session.execute(text(knn), {"v": v})} for v in probes]
    exact_ms = [_timed(session, knn, {"v": v})[1] for v in probes[:20]]
    session.execute(text("RESET enable_indexscan"))
    rows = [
        {
            "index": "none (exact scan)",
            "setting": "—",
            "build_s": None,
            "size_mb": None,
            "recall@10": 1.0,
            "p50_ms": percentile(exact_ms, 50),
            "p95_ms": percentile(exact_ms, 95),
        }
    ]

    lists = max(int(n**0.5), 10)
    for label, definition, settings in INDEX_VARIANTS:
        label, definition = label.format(lists=lists), definition.format(lists=lists)
        started = time.perf_counter()
        session.execute(text(f"CREATE INDEX bench_idx ON bench_vectors USING {definition}"))
        session.commit()
        build_s = round(time.perf_counter() - started, 2)
        size = session.execute(text("SELECT pg_relation_size('bench_idx')")).scalar_one()
        for name, value in settings:
            session.execute(text(f"SET {name} = {value}"))
            found, timings = [], []
            for v in probes:
                result, ms = _timed(session, knn, {"v": v})
                found.append({row[0] for row in result})
                timings.append(ms)
            recall = sum(len(f & e) for f, e in zip(found, exact, strict=True)) / (10 * len(probes))
            rows.append(
                {
                    "index": label,
                    "setting": f"{name}={value}",
                    "build_s": build_s,
                    "size_mb": round(size / 2**20, 1),
                    "recall@10": round(recall, 3),
                    "p50_ms": percentile(timings, 50),
                    "p95_ms": percentile(timings, 95),
                }
            )
            session.execute(text(f"RESET {name}"))
        session.execute(text("DROP INDEX bench_idx"))
        session.commit()
    session.execute(text("DROP TABLE bench_vectors"))
    session.commit()
    return rows


def partial_index_saving(session: Session) -> dict:
    counts = session.execute(
        text("SELECT count(*), count(*) FILTER (WHERE is_current) FROM extracted_fact")
    ).one()
    session.execute(text("CREATE INDEX bench_full ON extracted_fact (document_id, field_name)"))
    sizes = session.execute(
        text("SELECT pg_relation_size('ix_extracted_fact_current'), pg_relation_size('bench_full')")
    ).one()
    session.execute(text("DROP INDEX bench_full"))
    session.commit()
    return {
        "facts": counts[0],
        "current": counts[1],
        "partial_kb": round(sizes[0] / 1024, 1),
        "full_kb": round(sizes[1] / 1024, 1),
    }


def _table(rows: list[dict]) -> str:
    columns = list(rows[0])
    lines = ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    lines += [
        "| " + " | ".join("—" if r[c] is None else str(r[c]) for c in columns) + " |" for r in rows
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vectors", type=int, default=50_000, help="synthetic table size")
    parser.add_argument("--queries", type=int, default=100)
    parser.add_argument("--skip-index-study", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from anchor.db import get_sessionmaker
    from anchor.evals.__main__ import use_eval_database

    use_eval_database()
    OUT.mkdir(parents=True, exist_ok=True)
    with get_sessionmaker()() as session:
        latency, plans = retrieval_latency(session)
        for name, plan in plans.items():
            (OUT / f"explain-{name}.txt").write_text(plan + "\n", encoding="utf-8")
        partial = partial_index_saving(session)
        study = [] if args.skip_index_study else index_study(session, args.vectors, args.queries)

    report = [
        "# Performance report",
        "",
        "Hardware: see README. All numbers are wall-clock from the application side.",
        "",
        "## Retrieval latency on the eval corpus (k=10, warm)",
        "",
        _table(latency),
        "",
        "Query plans: [vector](explain-vector.txt), [text](explain-text.txt).",
        "",
        "## Partial index on current facts",
        "",
        "```json",
        json.dumps(partial, indent=2),
        "```",
    ]
    if study:
        report += [
            "",
            f"## Vector index study ({args.vectors:,} synthetic {DIMENSIONS}-d vectors, "
            f"{args.queries} queries)",
            "",
            "Random vectors are a pessimistic case for approximate indexes: real embeddings "
            "cluster, which raises recall at the same setting.",
            "",
            _table(study),
        ]
    (OUT / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report))


if __name__ == "__main__":
    main()
