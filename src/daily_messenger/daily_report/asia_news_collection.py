"""Bounded original-document intake for existing market-news adapter results."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlsplit

import requests

from .asia_news_contract import AsiaNewsCandidate, secure_source_url, validate_asia_candidate

DEFAULT_HOSTS = {"www.sse.com.cn", "www.szse.cn", "www.hkexnews.hk", "www.hkex.com.hk"}
DOCUMENT_LIMIT = 2 * 1024 * 1024


def _allowed_url(url: str, hosts: set[str]) -> str:
    secure_source_url(url)
    if urlsplit(url).hostname not in hosts:
        raise ValueError("source host not allowed")
    return url


@dataclass(frozen=True)
class BoundedDocumentFetcher:
    """No redirects; each request budget includes streamed body reading."""

    allowed_hosts: set[str]
    request: Callable = requests.get

    def __call__(self, url: str) -> bytes:
        _allowed_url(url, self.allowed_hosts)
        for attempt in range(2):
            try:
                return self._attempt(url)
            except (OSError, requests.RequestException):
                if attempt == 1:
                    raise ValueError("source fetch failed") from None
        raise ValueError("source fetch failed")

    def _attempt(self, url: str) -> bytes:
        deadline = time.monotonic() + 30
        with self.request(url, stream=True, timeout=(10, 30), allow_redirects=False) as response:
            if 300 <= response.status_code < 400:
                raise ValueError("source redirect rejected")
            response.raise_for_status()
            body = bytearray()
            for chunk in response.iter_content(chunk_size=65536):
                if time.monotonic() > deadline:
                    raise ValueError("source request timeout")
                body.extend(chunk)
                if len(body) > DOCUMENT_LIMIT:
                    raise ValueError("source document exceeds size limit")
            if not body:
                raise ValueError("empty source document")
            return bytes(body)


def _collect_one(
    item: Mapping[str, object],
    *,
    market: str,
    retrieved_at: datetime,
    collector_identity: str,
    fetch_document: Callable[[str], bytes],
    hosts: set[str],
) -> AsiaNewsCandidate:
    url = item.get("source_url")
    if not isinstance(url, str):
        raise ValueError("source URL missing")
    _allowed_url(url, hosts)
    # Validate metadata before requesting a document. Model approval fields are ignored.
    payload = {
        **item,
        "schema_version": "market_intel.asia_news_candidate.v1",
        "market": market,
        "retrieved_at": retrieved_at.isoformat(),
        "collector_identity": collector_identity,
        "source_sha256": "0" * 64,
    }
    validate_asia_candidate(payload)
    body = fetch_document(url)
    if not isinstance(body, bytes) or not body or len(body) > DOCUMENT_LIMIT:
        raise ValueError("invalid source bytes")
    payload["source_sha256"] = hashlib.sha256(body).hexdigest()
    return validate_asia_candidate(payload)


def collect_asia_candidates(
    items: Sequence[Mapping[str, object]],
    *,
    market: str,
    retrieved_at: datetime,
    collector_identity: str,
    fetch_document: Callable[[str], bytes],
    allowed_hosts: set[str] | None = None,
) -> tuple[list[AsiaNewsCandidate], list[dict[str, str]]]:
    """Adapt explicitly dated existing results; caller retains fetched bytes externally.

    A custom callback must bound its own I/O like BoundedDocumentFetcher. This
    function only validates returned bytes; it cannot interrupt arbitrary callbacks.
    """
    hosts = DEFAULT_HOSTS | (allowed_hosts or set())
    candidates: list[AsiaNewsCandidate] = []
    receipts: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        try:
            candidate = _collect_one(
                item,
                market=market,
                retrieved_at=retrieved_at,
                collector_identity=collector_identity,
                fetch_document=fetch_document,
                hosts=hosts,
            )
        except (ValueError, TypeError, KeyError, OSError, requests.RequestException):
            receipts.append(
                {"index": str(index), "status": "rejected", "reason": "source_fetch_failed"}
            )
            continue
        if candidate.evidence_id in seen:
            receipts.append({"index": str(index), "status": "duplicate"})
            continue
        seen.add(candidate.evidence_id)
        candidates.append(candidate)
        receipts.append({"index": str(index), "status": "needs_review"})
    return candidates, receipts
