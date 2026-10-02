import httpx
import pytest

from anchor.edgar import EdgarClient, EdgarError
from edgar_fakes import CIK, FakeEdgar


def test_client_refuses_to_start_without_a_user_agent() -> None:
    with pytest.raises(EdgarError, match="EDGAR_USER_AGENT"):
        EdgarClient("  ")


def test_every_request_identifies_the_caller() -> None:
    edgar = FakeEdgar()

    list(edgar.client().list_filings(CIK))

    assert edgar.requests[0].headers["User-Agent"] == "Test Suite test@example.com"
    assert edgar.requests[0].url.path == "/submissions/CIK0000320193.json"


def test_list_filings_keeps_only_requested_forms_that_have_a_document() -> None:
    filings = list(FakeEdgar().client().list_filings(CIK))

    assert [(f.form, f.accession_number) for f in filings] == [
        ("8-K/A", "0000320193-26-000030"),
        ("8-K", "0000320193-26-000015"),
    ]
    assert filings[0].company == "Example Corp"
    assert filings[0].filed_at.isoformat() == "2026-05-10T16:30:00+00:00"
    assert filings[0].url == (
        "https://www.sec.gov/Archives/edgar/data/320193/000032019326000030/amended.htm"
    )


def test_download_returns_the_raw_bytes() -> None:
    client = FakeEdgar().client()
    filing = next(client.list_filings(CIK))

    assert client.download(filing) == b"<html>Item 2.02 amended</html>"


def test_rate_limited_request_is_retried_after_the_advertised_delay() -> None:
    edgar = FakeEdgar()
    responses = iter([httpx.Response(429, headers={"Retry-After": "7"})])
    edgar.before = lambda request: next(responses, None)

    filings = list(edgar.client(min_interval=0).list_filings(CIK))

    assert len(filings) == 2
    assert len(edgar.requests) == 2
    assert edgar.sleeps == [7.0]


def test_server_errors_back_off_and_then_give_up() -> None:
    edgar = FakeEdgar()
    edgar.before = lambda request: httpx.Response(503)

    with pytest.raises(EdgarError, match="after 3 attempts: HTTP 503"):
        list(edgar.client(min_interval=0, max_retries=2).list_filings(CIK))

    assert len(edgar.requests) == 3
    assert edgar.sleeps == [1.0, 2.0]


def test_missing_document_fails_without_retrying() -> None:
    edgar = FakeEdgar()
    edgar.before = lambda request: httpx.Response(404)

    with pytest.raises(EdgarError, match="HTTP 404"):
        list(edgar.client(min_interval=0).list_filings(CIK))

    assert len(edgar.requests) == 1


def test_requests_are_spaced_to_respect_the_rate_limit() -> None:
    edgar = FakeEdgar()
    # Simulated time only moves while the client sleeps, so every request
    # appears to follow the previous one instantly.
    client = edgar.client(min_interval=0.125, clock=lambda: 100.0 + sum(edgar.sleeps))

    for filing in client.list_filings(CIK):
        client.download(filing)

    assert len(edgar.requests) == 3
    assert edgar.sleeps == [0.125, 0.125]
