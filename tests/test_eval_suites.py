import json
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from anchor.answer import AskConfig
from anchor.config import Settings
from anchor.evals import suites
from anchor.evals.suites import Corpus, RetrievalConfig, run_answers, run_extraction, run_retrieval
from anchor.extraction.extractor import extract_document
from anchor.indexing import index_document
from anchor.models import SourceDocument
from anchor.rerank import NoReranker
from anchor.storage import RawStore
from embed_fakes import FakeEmbedder
from llm_fakes import FakeLLM, FakeStreamingLLM

HTML = (
    b"<p>Item 1.01 Entry into a Material Definitive Agreement.</p>"
    b"<p>On September 2, 2026, Example Corp agreed to acquire Widget Inc. for $11.9 billion.</p>"
    b"<p>Item 5.02 Departure of Directors.</p><p>Jane Roe was appointed Chief Financial Officer.</p>"
)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


@pytest.fixture
def golden(tmp_path: Path, monkeypatch) -> Path:
    directory = tmp_path / "golden"
    directory.mkdir()
    write_jsonl(
        directory / "extraction.jsonl",
        [
            {
                "document": "doc-1",
                "facts": [
                    {
                        "field": "transaction_amount",
                        "value": "11900000000",
                        "quote": "for $11.9 billion",
                    },
                    {
                        "field": "counterparty",
                        "value": "Widget Inc.",
                        "quote": "acquire Widget Inc.",
                    },
                    {
                        "field": "officer_name",
                        "value": "Jane Roe",
                        "quote": "Jane Roe was appointed",
                    },
                ],
            }
        ],
    )
    write_jsonl(
        directory / "questions.jsonl",
        [
            {
                "id": "q1",
                "question": "Which company will Example Corp acquire?",
                "answerable": True,
                "key_facts": ["Widget Inc."],
                "evidence": [{"document": "doc-1", "quote": "agreed to acquire Widget Inc."}],
            },
            {
                "id": "u1",
                "question": "What is the dividend payout ratio?",
                "answerable": False,
                "key_facts": [],
                "evidence": [],
            },
        ],
    )
    monkeypatch.setattr(suites, "GOLDEN", directory)
    return directory


@pytest.fixture
def corpus(session: Session, tmp_path: Path, golden: Path) -> Corpus:
    store = RawStore(tmp_path / "raw")
    blob = store.put(HTML)
    document = SourceDocument(
        source_url="https://www.sec.gov/doc-1.htm",
        external_id="doc-1",
        doc_type="8-K",
        publisher="Example Corp",
        content_hash=blob.content_hash,
        raw_path=blob.relative_path,
    )
    session.add(document)
    session.commit()
    index_document(session, document, store, FakeEmbedder(), ("section",))
    extract_document(
        session,
        document,
        FakeLLM(
            [
                {
                    "field": "transaction_amount",
                    "value": "$11.9 billion",
                    "quote": "acquire Widget Inc. for $11.9 billion",
                    "confidence": 0.95,
                },
                {
                    "field": "counterparty",
                    "value": "Gadget LLC",
                    "quote": "acquire Gadget LLC",
                    "confidence": 0.9,
                },
                {
                    "field": "officer_name",
                    "value": "Jane Roe",
                    "quote": "Jane Roe was appointed",
                    "confidence": 0.95,
                },
            ]
        ),
        store,
        Settings(),
    )
    return Corpus(session, store)


def test_extraction_suite_scores_accuracy_provenance_and_hallucinations(session, corpus) -> None:
    result = run_extraction(session, corpus)

    metrics = result.metrics
    assert metrics["gold_fields"] == 3
    assert metrics["field_accuracy"] == pytest.approx(2 / 3, abs=1e-3)
    assert metrics["provenance_correctness"] == 1.0
    assert metrics["hallucination_rate"] == pytest.approx(1 / 3, abs=1e-3)
    missed = next(d for d in result.details if d["field"] == "counterparty")
    assert missed["found"] is None
    assert result.costs and result.latencies_ms


def test_retrieval_suite_finds_the_evidence_chunk(session, corpus) -> None:
    result = run_retrieval(session, corpus, FakeEmbedder(), RetrievalConfig("text", "section"))

    assert result.metrics["questions"] == 1
    assert result.metrics["recall@5"] == 1.0
    assert result.metrics["mrr"] == 1.0
    assert result.config["mode"] == "text"
    assert len(result.latencies_ms) == 1


def test_answer_suite_scores_accuracy_citations_and_refusals(session, corpus) -> None:
    line = {
        "claim": "Example Corp will acquire Widget Inc.",
        "source": "S1",
        "quote": "agreed to acquire Widget Inc.",
    }
    llm = FakeStreamingLLM(json.dumps(line) + "\n")
    sleeps: list[float] = []

    result = run_answers(
        session, corpus, embedder=FakeEmbedder(), reranker=NoReranker(), llm=llm,
        settings=Settings(), config=AskConfig(mode="text"), pause_seconds=2, sleep=sleeps.append,
    )  # fmt: skip

    metrics = result.metrics
    assert metrics["answer_accuracy"] == 1.0
    assert metrics["citation_correctness"] == 1.0
    # No chunk shares a word with the unanswerable question, so nothing is retrieved.
    assert metrics["refusal_rate_unanswerable"] == 1.0
    assert metrics["false_refusal_rate"] == 0.0
    assert sleeps == [2]
