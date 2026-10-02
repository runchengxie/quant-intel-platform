"""Candidate intake never treats reachable or allowlisted sources as approved."""

import time
from datetime import datetime
from hashlib import sha256

import pytest

from daily_messenger.daily_report.asia_news_collection import (
    BoundedDocumentFetcher,
    CollectionContext,
    collect_asia_candidates,
)
from tests.daily_report.test_asia_news_contract import candidate_payload

RETRIEVED = datetime.fromisoformat("2026-09-30T18:00:00+08:00")


def collect(items, fetch=lambda _: b"original disclosure", **kwargs):
    return collect_asia_candidates(
        items,
        market="cn",
        retrieved_at=RETRIEVED,
        fetch_document=fetch,
        context=CollectionContext("collector-a", frozenset(kwargs.get("allowed_hosts", set()))),
    )


def test_original_bytes_bound_and_duplicate_removed_without_approval():
    items, receipts = collect([candidate_payload(), candidate_payload()])
    assert len(items) == 1
    assert items[0].source_sha256 == sha256(b"original disclosure").hexdigest()
    assert items[0].published_at == "2026-09-30T14:00:00+08:00"
    assert [row["status"] for row in receipts] == ["needs_review", "duplicate"]
    assert not hasattr(items[0], "approved")


def test_existing_adapter_fields_keep_date_only_precision():
    items, receipts = collect(
        [
            {
                "url": "https://www.sse.com.cn/disclosure/x",
                "source": "SSE",
                "published_at": "2026-09-29",
                "title": "公告",
                "summary": "收入增长 6%。",
            }
        ]
    )
    assert len(items) == 1
    assert items[0].time_precision == "date"
    assert items[0].published_at == "2026-09-29"
    assert receipts[0]["status"] == "needs_review"


def test_content_revision_changes_identity():
    old = collect([candidate_payload()])[0][0]
    new = collect(
        [candidate_payload(document_status="revised", revision_of=old.evidence_id)],
        fetch=lambda _: b"revision",
    )[0][0]
    assert old.evidence_id != new.evidence_id
    assert new.revision_of == old.evidence_id


@pytest.mark.parametrize(
    "change",
    [
        {"published_at": ""},
        {"publisher": ""},
        {"source_url": "https://unknown.example/news"},
        {"source_url": "https://127.0.0.1/news"},
    ],
)
def test_invalid_or_unknown_source_never_enters_candidates(change):
    items, receipts = collect([candidate_payload(**change)])
    assert items == []
    assert receipts[0]["status"] == "rejected"


def test_fetch_failure_is_sanitized_and_empty_result_explicit():
    def fail(_):
        raise OSError("private token /home/user/secret")

    items, receipts = collect([candidate_payload()], fetch=fail)
    assert items == []
    assert receipts == [{"index": "0", "status": "rejected", "reason": "source_fetch_failed"}]
    assert collect([]) == ([], [])


def test_cancelled_candidate_retained_for_review_not_discarded_as_active():
    assert (
        collect([candidate_payload(document_status="cancelled")])[0][0].document_status
        == "cancelled"
    )


def test_explicit_extra_host_is_candidate_only():
    items, receipts = collect(
        [candidate_payload(source_url="https://issuer.example/disclosure")],
        allowed_hosts={"issuer.example"},
    )
    assert len(items) == 1
    assert receipts[0]["status"] == "needs_review"


class Response:
    status_code = 200

    def __init__(self, chunks):
        self.chunks = chunks

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def raise_for_status(self):
        if self.status_code >= 400:
            raise OSError("HTTP failure")

    def iter_content(self, chunk_size):
        assert chunk_size == 65536
        yield from self.chunks


def test_bounded_fetch_stream_limits_and_redirects():
    calls = []

    def request(url, **kwargs):
        calls.append((url, kwargs))
        return Response([b"x" * (2 * 1024 * 1024), b"y"])

    fetch = BoundedDocumentFetcher(allowed_hosts={"www.sse.com.cn"}, request=request)
    with pytest.raises(ValueError, match="size"):
        fetch("https://www.sse.com.cn/news")
    assert len(calls) == 1
    assert calls[0][1]["timeout"] == (10, 30)
    assert calls[0][1]["allow_redirects"] is False


def test_transient_request_never_exceeds_two_attempts():
    calls = []

    def request(*args, **kwargs):
        calls.append(1)
        raise OSError("private response")

    with pytest.raises(ValueError, match="fetch failed"):
        BoundedDocumentFetcher(allowed_hosts={"www.sse.com.cn"}, request=request)(
            "https://www.sse.com.cn/x"
        )
    assert len(calls) == 2


def test_successful_fetch_and_redirect_rejection():
    assert (
        BoundedDocumentFetcher(
            allowed_hosts={"www.sse.com.cn"}, request=lambda *a, **k: Response([b"a", b"b"])
        )("https://www.sse.com.cn/x")
        == b"ab"
    )
    response = Response([b"redirect"])
    response.status_code = 302
    with pytest.raises(ValueError, match="redirect"):
        BoundedDocumentFetcher(allowed_hosts={"www.sse.com.cn"}, request=lambda *a, **k: response)(
            "https://www.sse.com.cn/x"
        )


def test_wall_clock_budget_interrupts_a_stream_that_never_yields(monkeypatch):
    import daily_messenger.daily_report.asia_news_collection as collection

    class SlowResponse(Response):
        def iter_content(self, chunk_size):
            time.sleep(0.3)
            yield b"late"

    monkeypatch.setattr(collection, "ATTEMPT_SECONDS", 0.03, raising=False)
    started = time.monotonic()
    with pytest.raises(ValueError, match="timeout"):
        BoundedDocumentFetcher({"www.sse.com.cn"}, lambda *a, **k: SlowResponse([]))(
            "https://www.sse.com.cn/x"
        )
    assert time.monotonic() - started < 0.2
