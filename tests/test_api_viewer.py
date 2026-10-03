from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from anchor.api import main
from anchor.config import Settings
from anchor.db import get_session
from anchor.extraction.extractor import extract_document
from anchor.models import SourceDocument
from anchor.storage import RawStore
from anchor.text import html_to_text
from llm_fakes import FakeLLM

HTML = b"<p>Item 5.02</p><p>Jane Roe was appointed Chief Financial Officer.</p>"


@pytest.fixture
def client(session: Session, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(main, "get_settings", lambda: Settings(raw_storage_dir=tmp_path))
    main.app.dependency_overrides[get_session] = lambda: session
    with TestClient(main.app) as client:
        yield client
    main.app.dependency_overrides.clear()


@pytest.fixture
def document(session: Session, tmp_path: Path) -> SourceDocument:
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
    fact = {"field": "officer_name", "value": "Jane Roe", "quote": "Jane Roe was appointed",
            "confidence": 0.9}  # fmt: skip
    extract_document(session, document, FakeLLM([fact]), store, Settings())
    return document


def test_viewer_page_is_served(client) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "<title>Anchor — Verifiable Answers</title>" in response.text


def test_document_text_is_the_text_spans_refer_to(client, document) -> None:
    body = client.get(f"/documents/{document.id}/text").json()
    fact = client.get(f"/documents/{document.id}/facts").json()[0]

    assert body["text"] == html_to_text(HTML)
    assert body["text"][fact["span_start"] : fact["span_end"]] == "Jane Roe"


def test_run_details_expose_model_and_versions(client, document) -> None:
    fact = client.get(f"/documents/{document.id}/facts").json()[0]

    run = client.get(f"/runs/{fact['run_id']}").json()

    assert (run["model_name"], run["model_version"]) == ("fake-model", "fake-001")
    assert run["prompt_version"] == "p1"


def test_unknown_ids_return_404(client) -> None:
    missing = "00000000-0000-0000-0000-000000000000"

    assert client.get(f"/documents/{missing}/text").status_code == 404
    assert client.get(f"/runs/{missing}").status_code == 404
