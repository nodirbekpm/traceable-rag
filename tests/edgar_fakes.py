"""An in-memory EDGAR for tests: no network, deterministic responses."""

from collections.abc import Callable

import httpx

from anchor.edgar import EdgarClient

CIK = 320193

SUBMISSIONS = {
    "cik": str(CIK),
    "name": "Example Corp",
    "filings": {
        "recent": {
            "accessionNumber": [
                "0000320193-26-000030",
                "0000320193-26-000020",
                "0000320193-26-000015",
                "0000320193-26-000010",
            ],
            "form": ["8-K/A", "10-Q", "8-K", "8-K"],
            "acceptanceDateTime": [
                "2026-05-10T16:30:00.000Z",
                "2026-05-02T16:30:00.000Z",
                "2026-05-01T16:30:00.000Z",
                "2026-02-01T16:30:00.000Z",
            ],
            "primaryDocument": ["amended.htm", "q2.htm", "results.htm", ""],
        }
    },
}

DOCUMENTS = {
    "/Archives/edgar/data/320193/000032019326000030/amended.htm": b"<html>Item 2.02 amended</html>",
    "/Archives/edgar/data/320193/000032019326000015/results.htm": b"<html>Item 2.02 results</html>",
}


class FakeEdgar:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.sleeps: list[float] = []
        self.before: Callable[[httpx.Request], httpx.Response | None] = lambda request: None

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        override = self.before(request)
        if override is not None:
            return override
        if request.url.host == "data.sec.gov":
            return httpx.Response(200, json=SUBMISSIONS)
        body = DOCUMENTS.get(request.url.path)
        return httpx.Response(200, content=body) if body is not None else httpx.Response(404)

    def downloads(self) -> list[str]:
        return [r.url.path for r in self.requests if r.url.host == "www.sec.gov"]

    def client(self, **kwargs) -> EdgarClient:
        return EdgarClient(
            "Test Suite test@example.com",
            transport=httpx.MockTransport(self.handle),
            sleep=self.sleeps.append,
            **kwargs,
        )
