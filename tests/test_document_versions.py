from contextlib import nullcontext
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from anchor import analysis
from anchor.api import main
from anchor.config import Settings
from anchor.db import get_session
from anchor.models import Chunk, ExtractedFact, SourceDocument
from anchor.storage import RawStore
from embed_fakes import FakeEmbedder
from llm_fakes import FakeLLM

V1 = (
    "SERVICE AGREEMENT\n\nSigned on January 15, 2026 by Brightline Analytics Inc.\n\n"
    "The annual fee is $84,000. Either party may terminate with 60 days notice."
)
V2 = (
    "SERVICE AGREEMENT (AMENDED)\n\nSigned on January 15, 2026 by Brightline Analytics Inc.\n\n"
    "The annual fee is $90,000. Overdue amounts bear interest of 1.25% per month."
)


def fact(field: str, value: str, quote: str, entity: str | None = None) -> dict:
    return {"field": field, "value": value, "quote": quote, "entity": entity, "confidence": 0.95}


V1_FACTS = [
    fact("document_date", "January 15, 2026", "Signed on January 15, 2026"),
    fact("monetary_amount", "$84,000", "The annual fee is $84,000", "annual fee"),
    fact("duration", "60 days", "terminate with 60 days notice", "termination notice"),
]
V2_FACTS = [
    fact("document_date", "January 15, 2026", "Signed on January 15, 2026"),
    fact("monetary_amount", "$90,000", "The annual fee is $90,000", "annual fee"),
    fact("percentage", "1.25%", "interest of 1.25% per month", "late interest"),
]


@pytest.fixture
def client(session: Session, tmp_path: Path, monkeypatch):
    settings = Settings(raw_storage_dir=tmp_path)
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    main.app.dependency_overrides[get_session] = lambda: session
    main.app.dependency_overrides[main.get_session_factory] = lambda: lambda: nullcontext(session)
    analysis._jobs.clear()
    with TestClient(main.app) as client:
        client.tmp_path = tmp_path
        yield client
    main.app.dependency_overrides.clear()


def analyse(client, document_id: str, facts: list[dict]) -> None:
    main.app.dependency_overrides[main.get_analysis_components] = lambda: {
        "llm": FakeLLM(facts),
        "embedder": FakeEmbedder(),
        "store": RawStore(client.tmp_path),
        "settings": Settings(raw_storage_dir=client.tmp_path),
    }
    client.post(f"/documents/{document_id}/analyze")
    assert client.get(f"/documents/{document_id}/status").json()["state"] == "ready"


@pytest.fixture
def versions(client) -> tuple[str, str]:
    first = client.post("/documents", files={"file": ("contract.txt", V1.encode())}).json()
    analyse(client, first["document"]["id"], V1_FACTS)
    second = client.post(
        f"/documents/{first['document']['id']}/versions",
        files={"file": ("contract-v2.txt", V2.encode())},
    )
    assert second.status_code == 201, second.text
    assert second.json()["document"]["version"] == 2
    analyse(client, second.json()["document"]["id"], V2_FACTS)
    return first["document"]["id"], second.json()["document"]["id"]


def facts_of(session: Session, document_id: str) -> dict[str, ExtractedFact]:
    rows = session.scalars(select(ExtractedFact).where(ExtractedFact.document_id == document_id))
    return {row.field_name: row for row in rows}


def test_new_version_retires_every_old_fact_and_links_restated_ones(session, versions) -> None:
    v1, v2 = versions

    old, new = facts_of(session, v1), facts_of(session, v2)

    assert not any(f.is_current for f in old.values())
    assert all(f.is_current for f in new.values())
    assert old["monetary_amount"].superseded_by == new["monetary_amount"].id
    assert old["document_date"].superseded_by == new["document_date"].id
    assert old["duration"].superseded_by is None


def test_changes_list_what_was_changed_added_and_removed(client, versions) -> None:
    _, v2 = versions

    changes = client.get(f"/documents/{v2}/changes").json()["changes"]

    summary = {(c["change"], c["field"], c["before"], c["after"]) for c in changes}
    assert summary == {
        ("changed", "monetary_amount", "$84,000", "$90,000"),
        ("removed", "duration", "60 days", None),
        ("added", "percentage", None, "1.25%"),
    }


def test_history_of_a_value_reaches_back_into_the_old_version(client, session, versions) -> None:
    _, v2 = versions
    fee = facts_of(session, v2)["monetary_amount"]

    history = client.get(f"/facts/{fee.id}/history").json()

    assert [h["value_raw"] for h in history] == ["$90,000", "$84,000"]


def test_document_list_marks_versions_and_the_latest(client, versions) -> None:
    v1, v2 = versions

    listed = {d["id"]: d for d in client.get("/documents").json()}
    chain = client.get(f"/documents/{v1}/versions").json()

    assert (listed[v1]["version"], listed[v1]["is_latest"]) == (1, False)
    assert (listed[v2]["version"], listed[v2]["is_latest"]) == (2, True)
    assert [d["title"] for d in chain] == ["contract.txt", "contract-v2.txt"]


def test_invalid_versions_are_refused(client, versions) -> None:
    v1, v2 = versions

    on_old = client.post(f"/documents/{v1}/versions", files={"file": ("c.txt", b"new text")})
    same = client.post(f"/documents/{v2}/versions", files={"file": ("c.txt", V2.encode())})

    assert on_old.status_code == 409
    assert "newer version" in on_old.json()["detail"]
    assert same.status_code == 409


def test_delete_removes_every_version_with_its_data_and_files(client, session, versions) -> None:
    v1, v2 = versions
    store = RawStore(client.tmp_path)
    paths = [session.get(SourceDocument, v).raw_path for v in (v1, v2)]

    response = client.delete(f"/documents/{v2}")

    assert response.json() == {"deleted_versions": 2}
    assert session.scalar(select(func.count()).select_from(SourceDocument)) == 0
    assert session.scalar(select(func.count()).select_from(ExtractedFact)) == 0
    assert session.scalar(select(func.count()).select_from(Chunk)) == 0
    for path in paths:
        with pytest.raises(FileNotFoundError):
            store.get(path)
    assert client.get(f"/documents/{v1}/text").status_code == 404


def test_filings_cannot_be_deleted_or_versioned(client, session) -> None:
    store = RawStore(client.tmp_path)
    blob = store.put(b"<p>Item 2.02</p>")
    filing = SourceDocument(
        source_url="https://www.sec.gov/x.htm", doc_type="8-K", publisher="Example Corp",
        content_hash=blob.content_hash, raw_path=blob.relative_path,
    )  # fmt: skip
    session.add(filing)
    session.commit()

    deleted = client.delete(f"/documents/{filing.id}")
    versioned = client.post(f"/documents/{filing.id}/versions", files={"file": ("x.txt", b"x")})

    assert deleted.status_code == 403
    assert versioned.status_code == 409
    assert session.get(SourceDocument, filing.id) is not None


def test_same_value_under_a_different_label_is_not_reported_as_changed(client, session) -> None:
    first = client.post("/documents", files={"file": ("c.txt", V1.encode())}).json()
    analyse(client, first["document"]["id"], V1_FACTS)
    second = client.post(
        f"/documents/{first['document']['id']}/versions",
        files={"file": ("c2.txt", V1.replace("$84,000", "$85,000").encode())},
    ).json()
    relabelled = [
        fact("document_date", "January 15, 2026", "Signed on January 15, 2026", "signature date"),
        fact("monetary_amount", "$85,000", "The annual fee is $85,000", "annual fee"),
        fact("duration", "60 days", "terminate with 60 days notice", "notice to terminate"),
    ]
    analyse(client, second["document"]["id"], relabelled)

    changes = client.get(f"/documents/{second['document']['id']}/changes").json()["changes"]

    assert [(c["change"], c["before"], c["after"]) for c in changes] == [
        ("changed", "$84,000", "$85,000")
    ]
