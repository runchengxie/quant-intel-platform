"""Operational quote recovery stays strict about provenance and observation time."""

import hashlib
import json
from datetime import UTC, datetime

import pytest

from a_share_daily.cross_market_index_receipt import recover_indices


@pytest.fixture
def receipt(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    raw = b"ts_code,trade_date,close\nHSI,20261020,100\nHSI,20261021,101\n"
    (run / "HSI.csv").write_bytes(raw)
    payload = {
        "protocol": "overseas-index-operational-v1",
        "requested_date": "20261021",
        "started_utc": "2026-10-22T00:00:00+00:00",
        "completed_utc": "2026-10-22T00:00:02+00:00",
        "status": "complete",
        "sources": {
            "HSI": {
                "status": "ok",
                "api": "index_global",
                "provider": "tushare-compatible",
                "file": "HSI.csv",
                "sha256": hashlib.sha256(raw).hexdigest(),
                "rows": 2,
                "source_dates": ["20261020", "20261021"],
                "request_started_utc": "2026-10-22T00:00:00+00:00",
                "request_completed_utc": "2026-10-22T00:00:01+00:00",
            }
        },
    }
    p = run / "receipt.json"
    p.write_text(json.dumps(payload))
    return tmp_path, p, payload


def base():
    return {
        "date": "20261021",
        "us_stocks": {
            "^HSI": {"error": "insufficient data"},
            "SPY": {"close": 100, "as_of_date": "2026-10-21"},
        },
        "errors": ["^HSI: insufficient data", "^TNX: unavailable"],
    }


def apply(receipt):
    root, path, _ = receipt
    return recover_indices(
        base(), path, root=root, observed_at=datetime(2026, 10, 22, 1, tzinfo=UTC)
    )


def test_recovers_only_missing_index_and_retains_other_errors(receipt):
    result = apply(receipt)
    assert result["us_stocks"]["^HSI"]["close"] == 101
    assert result["us_stocks"]["^HSI"]["pct_chg"] == 1
    assert result["us_stocks"]["^HSI"]["as_of_date"] == "2026-10-21"
    assert result["us_stocks"]["^HSI"]["source"] == "tushare-compatible"
    assert "^TNX: unavailable" in result["errors"]
    assert not any(x.startswith("^HSI:") for x in result["errors"])
    assert result["us_stocks"]["SPY"] == base()["us_stocks"]["SPY"]
    assert result["_index_recovery"]["recovered"] == ["^HSI"]


@pytest.mark.parametrize(
    "change",
    [
        "protocol",
        "date",
        "future",
        "hash",
        "rows",
        "path",
        "symbol",
        "duplicate",
        "missing",
        "nan",
        "zero",
        "future_session",
        "time_order",
        "source_dates",
    ],
)
def test_rejects_invalid_receipt_without_replacing_original(receipt, change):  # noqa: PLR0912 - explicit mutation matrix
    _root, path, p = receipt
    s = p["sources"]["HSI"]
    if change == "protocol":
        p["protocol"] = "overseas-receipt-v1"
    elif change == "date":
        p["requested_date"] = "20261020"
    elif change == "future":
        p["completed_utc"] = "2026-10-22T02:00:00+00:00"
    elif change == "hash":
        s["sha256"] = "0" * 64
    elif change == "rows":
        s["rows"] = 3
    elif change == "path":
        s["file"] = "../HSI.csv"
    elif change == "time_order":
        s["request_started_utc"] = "2026-10-21T00:00:00+00:00"
    elif change == "source_dates":
        s["source_dates"] = ["20261021"]
    else:
        raw = (path.parent / "HSI.csv").read_bytes()
        if change == "symbol":
            raw = raw.replace(b"HSI", b"KS11")
        elif change == "duplicate":
            raw += raw.splitlines()[-1] + b"\n"
            s["rows"] = 3
        elif change == "missing":
            raw = raw.replace(b"20261021", b"20261019")
        elif change == "nan":
            raw = raw.replace(b",101", b",nan")
        elif change == "zero":
            raw = raw.replace(b",101", b",0")
        elif change == "future_session":
            raw += b"HSI,20261022,103\n"
            s["rows"] = 3
        (path.parent / "HSI.csv").write_bytes(raw)
        s["sha256"] = hashlib.sha256(raw).hexdigest()
    path.write_text(json.dumps(p))
    result = apply(receipt)
    assert result["us_stocks"]["^HSI"] == base()["us_stocks"]["^HSI"]
    assert result["_index_recovery"]["recovered"] == []
    assert result["_index_recovery"]["rejections"]


def test_symlink_escape_is_rejected(receipt):
    root, path, _p = receipt
    original = path.parent / "HSI.csv"
    external = root / "other.csv"
    original.rename(external)
    original.symlink_to(external)
    assert not apply(receipt)["_index_recovery"]["recovered"]


def test_valid_first_choice_is_preserved(receipt):
    root, path, _ = receipt
    data = base()
    data["us_stocks"]["^HSI"] = {"close": 99, "as_of_date": "2026-10-21"}
    result = recover_indices(
        data, path, root=root, observed_at=datetime(2026, 10, 22, 1, tzinfo=UTC)
    )
    assert result["us_stocks"]["^HSI"]["close"] == 99


def test_recovery_cli_never_fetches_network(receipt, monkeypatch, tmp_path):
    import sys

    from a_share_daily import fallback_fetch

    root, path, _ = receipt
    snapshot = tmp_path / "input.json"
    snapshot.write_text(json.dumps(base()))
    monkeypatch.setattr(fallback_fetch, "run", lambda *a, **k: pytest.fail("second live fetch"))
    written = []
    monkeypatch.setattr(fallback_fetch, "_write_snapshot", lambda data, day: written.append(data))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "fallback_fetch",
            "--date",
            "20261021",
            "--recover-receipt",
            str(path),
            "--receipt-root",
            str(root),
            "--input-snapshot",
            str(snapshot),
            "--observed-at",
            "2026-10-22T01:00:00+00:00",
        ],
    )
    assert fallback_fetch.main() == 1
    assert written[0]["us_stocks"]["^HSI"]["close"] == 101
    assert "^TNX: unavailable" in written[0]["errors"]


def test_provenance_and_malformed_original_quote(receipt):
    root, path, payload = receipt
    payload["sources"]["HSI"]["route_host"] = "provider.example"
    path.write_text(json.dumps(payload))
    data = base()
    data["us_stocks"]["^HSI"] = None
    result = recover_indices(
        data, path, root=root, observed_at=datetime(2026, 10, 22, 1, tzinfo=UTC)
    )
    quote = result["us_stocks"]["^HSI"]
    assert quote["route_host"] == "provider.example"
    assert quote["receipt_path"] == str(path.resolve())


@pytest.mark.parametrize("failure", ["oversize_receipt", "oversize_csv", "interrupted"])
def test_unusable_receipt_preserves_original(receipt, failure):
    _, path, _ = receipt
    if failure == "interrupted":
        path.rename(path.with_name("started.json"))
    elif failure == "oversize_csv":
        (path.parent / "HSI.csv").write_bytes(b"x" * 4_000_001)
    else:
        path.write_bytes(b"x" * 1_000_001)
    assert apply(receipt)["us_stocks"]["^HSI"] == base()["us_stocks"]["^HSI"]
