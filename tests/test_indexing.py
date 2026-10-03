from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from anchor.indexing import index_document
from anchor.models import EMBEDDING_DIMENSIONS, Chunk, SourceDocument
from anchor.storage import RawStore
from anchor.text import html_to_text
from embed_fakes import FakeEmbedder

HTML = (
    b"<p>FORM 8-K</p>"
    b"<p>Item 2.02 Results of Operations and Financial Condition.</p>"
    b"<p>Example Corp reported revenue of $4.2 million for the quarter.</p>"
    b"<p>Item 5.02 Departure of Directors or Certain Officers.</p>"
    b"<p>Jane Roe was appointed Chief Financial Officer.</p>"
)


@pytest.fixture
def document(session: Session, tmp_path: Path) -> tuple[SourceDocument, RawStore]:
    store = RawStore(tmp_path)
    blob = store.put(HTML)
    document = SourceDocument(
        source_url="https://www.sec.gov/x.htm",
        doc_type="8-K",
        publisher="Example Corp",
        content_hash=blob.content_hash,
        raw_path=blob.relative_path,
    )
    session.add(document)
    session.commit()
    return document, store


def test_all_strategies_are_indexed_and_chunks_slice_the_source(session, document) -> None:
    doc, store = document

    result = index_document(session, doc, store, FakeEmbedder())

    source = html_to_text(HTML)
    chunks = session.scalars(select(Chunk).where(Chunk.document_id == doc.id)).all()
    assert result.chunks == len(chunks) > 0
    assert {c.chunk_strategy for c in chunks} == {"fixed", "sentence", "section"}
    for chunk in chunks:
        assert chunk.text == source[chunk.span_start : chunk.span_end]
        assert len(chunk.embedding) == EMBEDDING_DIMENSIONS
    sections = {c.section for c in chunks if c.chunk_strategy == "section"}
    assert sections == {"preamble", "2.02", "5.02"}


def test_indexing_twice_adds_nothing_and_embeds_nothing(session, document) -> None:
    doc, store = document
    index_document(session, doc, store, FakeEmbedder())
    embedder = FakeEmbedder()

    result = index_document(session, doc, store, embedder)

    assert (result.chunks, result.skipped_strategies) == (0, 3)
    assert embedder.calls == 0


def test_a_new_strategy_can_be_added_later(session, document) -> None:
    doc, store = document
    index_document(session, doc, store, FakeEmbedder(), ("fixed",))

    result = index_document(session, doc, store, FakeEmbedder())

    assert result.skipped_strategies == 1
    strategies = session.scalars(select(Chunk.chunk_strategy).distinct()).all()
    assert set(strategies) == {"fixed", "sentence", "section"}


def test_embedder_with_the_wrong_dimension_is_refused(session, document) -> None:
    doc, store = document

    with pytest.raises(ValueError, match="migration is required"):
        index_document(session, doc, store, FakeEmbedder(dimensions=768))


def test_keyword_search_finds_exact_tokens(session, document) -> None:
    doc, store = document
    index_document(session, doc, store, FakeEmbedder(), ("section",))

    hits = session.scalars(
        select(Chunk.section).where(
            Chunk.tsv.op("@@")(func.websearch_to_tsquery("english", "appointed officer"))
        )
    ).all()

    assert hits == ["5.02"]


def test_vector_search_returns_the_nearest_chunk(session, document) -> None:
    doc, store = document
    embedder = FakeEmbedder()
    index_document(session, doc, store, embedder, ("section",))
    target = session.scalar(select(Chunk).where(Chunk.section == "2.02"))

    nearest = session.scalar(
        select(Chunk).order_by(Chunk.embedding.cosine_distance(embedder.embed_query(target.text)))
    )

    assert nearest.id == target.id


def test_vector_and_text_indexes_exist(session) -> None:
    rows = session.execute(
        text("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'chunk'")
    ).all()
    definitions = dict(rows)

    assert "USING hnsw" in definitions["ix_chunk_embedding_hnsw"]
    assert "vector_cosine_ops" in definitions["ix_chunk_embedding_hnsw"]
    assert "USING gin" in definitions["ix_chunk_tsv"]
