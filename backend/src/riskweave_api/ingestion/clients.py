from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .rate_limit import RateLimiter

MAX_JSON_BYTES = 25 * 1024 * 1024
MAX_FILING_BYTES = 50 * 1024 * 1024


class ProviderError(RuntimeError):
    """Sanitized provider failure that never includes request URLs or credentials."""


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


_OPENER = build_opener(_RejectRedirects)


def _read(request: Request, *, max_bytes: int, expected_content_types: tuple[str, ...]) -> bytes:
    try:
        with _OPENER.open(request, timeout=30) as response:
            content_type = response.headers.get_content_type()
            if content_type not in expected_content_types:
                raise ProviderError("provider returned an unexpected content type")
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise ProviderError("provider response exceeded the configured size limit")
            return body
    except (HTTPError, URLError, TimeoutError) as exc:
        raise ProviderError("provider request failed") from exc


class SecClient:
    def __init__(self, user_agent: str, *, limiter: RateLimiter | None = None) -> None:
        if "@" not in user_agent:
            raise ValueError("SEC User-Agent must identify a contact email")
        self._headers = {"User-Agent": user_agent, "Accept-Encoding": "identity"}
        self._limiter = limiter or RateLimiter(10)

    def _get(self, url: str, *, max_bytes: int = MAX_JSON_BYTES) -> bytes:
        if not url.startswith(("https://data.sec.gov/", "https://www.sec.gov/Archives/")):
            raise ValueError("unapproved SEC host")
        self._limiter.acquire()
        types = ("application/json",) if url.endswith(".json") else ("text/html", "text/plain")
        return _read(
            Request(url, headers=self._headers), max_bytes=max_bytes, expected_content_types=types
        )

    def submissions(self, cik: str) -> dict[str, Any]:
        return json.loads(self._get(f"https://data.sec.gov/submissions/CIK{cik}.json"))

    def submissions_file(self, name: str) -> dict[str, Any]:
        if not name.startswith("CIK") or not name.endswith(".json") or "/" in name:
            raise ValueError("invalid SEC submissions filename")
        return json.loads(self._get(f"https://data.sec.gov/submissions/{name}"))

    def companyfacts(self, cik: str) -> dict[str, Any]:
        return json.loads(self._get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"))

    def filing(self, cik: str, accession: str, primary_document: str) -> tuple[str, str]:
        compact = accession.replace("-", "")
        url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{compact}/{primary_document}"
        return url, self._get(url, max_bytes=MAX_FILING_BYTES).decode("utf-8", errors="replace")


class FredClient:
    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("FRED_API_KEY is required")
        self._api_key = api_key

    def _get(self, path: str, **params: str) -> dict[str, Any]:
        query = urlencode({"api_key": self._api_key, "file_type": "json", **params})
        url = f"https://api.stlouisfed.org/fred/{path}?{query}"
        body = _read(
            Request(url, headers={"Accept": "application/json"}),
            max_bytes=MAX_JSON_BYTES,
            expected_content_types=("application/json",),
        )
        return json.loads(body)

    def series(self, series_id: str) -> dict[str, Any]:
        return self._get("series", series_id=series_id)

    def observations(self, series_id: str) -> dict[str, Any]:
        return self._get("series/observations", series_id=series_id)
