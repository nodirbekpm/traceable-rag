from sqlalchemy import text
from sqlalchemy.orm import Session

from anchor.bench import index_study, partial_index_saving


def test_index_study_reports_every_variant_and_cleans_up(session: Session) -> None:
    rows = index_study(session, n=300, queries=5)

    assert rows[0]["index"] == "none (exact scan)"
    assert {row["index"].split()[0] for row in rows[1:]} == {"hnsw", "ivfflat"}
    assert all(0 <= row["recall@10"] <= 1 for row in rows)
    assert all(row["size_mb"] is not None for row in rows[1:])
    leftover = session.execute(text("SELECT to_regclass('bench_vectors')")).scalar_one()
    assert leftover is None


def test_partial_index_report_has_both_sizes(session: Session) -> None:
    report = partial_index_saving(session)

    assert set(report) == {"facts", "current", "partial_kb", "full_kb"}
    exists = session.execute(text("SELECT to_regclass('bench_full')")).scalar_one()
    assert exists is None
