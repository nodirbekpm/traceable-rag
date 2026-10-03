"""Minimal SEC EDGAR client: list a company's filings and download primary documents.

SEC fair-access rules: identify yourself in the User-Agent and stay under 10 requests/second.
https://www.sec.gov/os/accessing-edgar-data
"""

import re
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Self

import httpx

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"
INDEX_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/index.json"

# Press releases with the actual numbers are usually attached as Exhibit 99.x,
# named e.g. "a8-kex991q3.htm" or "ef2006_ex99-1.htm".
_EXHIBIT_99 = re.compile(r"ex[-_]?99(?:[-_.]?(\d))?", re.IGNORECASE)

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class EdgarError(RuntimeError):
    pass


@dataclass(frozen=True)
class Filing:
    cik: int
    company: str
    accession_number: str
    form: str
    filed_at: datetime
    primary_document: str

    @property
    def url(self) -> str:
        return ARCHIVE_URL.format(
            cik=self.cik,
            accession=self.accession_number.replace("-", ""),
            document=self.primary_document,
        )


@dataclass(frozen=True)
class Exhibit:
    filing: Filing
    name: str
    doc_type: str

    @property
    def url(self) -> str:
        return ARCHIVE_URL.format(
            cik=self.filing.cik,
            accession=self.filing.accession_number.replace("-", ""),
            document=self.name,
        )

    @property
    def external_id(self) -> str:
        return f"{self.filing.accession_number}/{self.name}"


class EdgarClient:
    def __init__(
        self,
        user_agent: str,
        *,
        transport: httpx.BaseTransport | None = None,
        min_interval: float = 0.125,
        max_retries: int = 3,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not user_agent.strip():
            raise EdgarError(
                "EDGAR_USER_AGENT is not set. SEC requires a contact string, "
                'for example "Jane Doe jane@example.com".'
            )
        self._http = httpx.Client(
            headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"},
            transport=transport,
            timeout=30.0,
            follow_redirects=True,
        )
        self._min_interval = min_interval
        self._max_retries = max_retries
        self._sleep = sleep
        self._clock = clock
        self._last_request_at: float | None = None

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._http.close()

    def list_filings(self, cik: int, forms: tuple[str, ...] = ("8-K", "8-K/A")) -> Iterator[Filing]:
        """Yield the company's recent filings of the given form types, newest first."""
        payload = self._get(SUBMISSIONS_URL.format(cik=cik)).json()
        recent = payload["filings"]["recent"]
        rows = zip(
            recent["accessionNumber"],
            recent["form"],
            recent["acceptanceDateTime"],
            recent["primaryDocument"],
            strict=True,
        )
        for accession, form, accepted, document in rows:
            # A few old filings have no primary document; there is nothing to store for them.
            if form not in forms or not document:
                continue
            yield Filing(
                cik=cik,
                company=payload["name"],
                accession_number=accession,
                form=form,
                filed_at=datetime.fromisoformat(accepted),
                primary_document=document,
            )

    def list_exhibits(self, filing: Filing) -> list[Exhibit]:
        """Exhibit 99 documents (press releases) attached to a filing."""
        url = INDEX_URL.format(cik=filing.cik, accession=filing.accession_number.replace("-", ""))
        exhibits = []
        for item in self._get(url).json()["directory"]["item"]:
            name = item["name"]
            match = _EXHIBIT_99.search(name)
            if match is None or not name.lower().endswith((".htm", ".html")):
                continue
            doc_type = f"EX-99.{match.group(1)}" if match.group(1) else "EX-99"
            exhibits.append(Exhibit(filing=filing, name=name, doc_type=doc_type))
        return exhibits

    def download_url(self, url: str) -> bytes:
        return self._get(url).content

    def download(self, filing: Filing) -> bytes:
        """Return the primary document exactly as served, with no decoding or cleanup."""
        return self._get(filing.url).content

    def _get(self, url: str) -> httpx.Response:
        last_error: str = ""
        for attempt in range(self._max_retries + 1):
            self._throttle()
            try:
                response = self._http.get(url)
            except httpx.TransportError as exc:
                last_error = repr(exc)
            else:
                if response.status_code not in RETRYABLE_STATUS:
                    if response.is_error:
                        raise EdgarError(f"GET {url} failed with HTTP {response.status_code}")
                    return response
                last_error = f"HTTP {response.status_code}"
                retry_after = response.headers.get("Retry-After", "")
                if retry_after.isdigit():
                    self._sleep(float(retry_after))
                    continue
            if attempt < self._max_retries:
                self._sleep(2.0**attempt)
        raise EdgarError(f"GET {url} failed after {self._max_retries + 1} attempts: {last_error}")

    def _throttle(self) -> None:
        now = self._clock()
        if self._last_request_at is not None:
            wait = self._min_interval - (now - self._last_request_at)
            if wait > 0:
                self._sleep(wait)
                now += wait
        self._last_request_at = now
