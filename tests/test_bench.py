from sqlalchemy import text
from sqlalchemy.orm import Session

from anchor.bench import index_study, partial_index_saving


def test_index_study_reports_every_variant_and_cleans_up(session: Session) -> None:
    rows, source = index_study(session, n=300, queries=5)

    assert rows[0]["index"] == "none (exact scan)"
    assert source.startswith("random vectors")
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


def test_index_study_grows_real_embeddings_when_chunks_exist(session: Session, tmp_path) -> None:
    from anchor.indexing import index_document
    from anchor.models import SourceDocument
    from anchor.storage import RawStore
    from embed_fakes import FakeEmbedder

    store = RawStore(tmp_path)
    blob = store.put(
        b"<p>Item 2.02</p><p>Revenue was $4.2 million.</p><p>Item 5.02</p><p>Jane Roe.</p>"
    )
    document = SourceDocument(
        source_url="https://www.sec.gov/x.htm", doc_type="8-K", publisher="Example Corp",
        content_hash=blob.content_hash, raw_path=blob.relative_path,
    )  # fmt: skip
    session.add(document)
    session.commit()
    index_document(session, document, store, FakeEmbedder())

    rows, source = index_study(session, n=200, queries=5)

    assert "real chunk embeddings" in source
    assert all(0 <= row["recall@10"] <= 1 for row in rows)
