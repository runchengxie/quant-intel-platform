import hashlib
import json
import socket
import subprocess
from datetime import UTC, datetime
from importlib import import_module

import pytest

from daily_messenger.daily_report.serialization import dumps_json

REVISED_AT = datetime(2026, 10, 4, 1, tzinfo=UTC)


def _legacy_digest(payload):
    def normalize(value, key=""):
        if isinstance(value, dict):
            return {name: normalize(item, name) for name, item in value.items()}
        if isinstance(value, list):
            return [normalize(item) for item in value]
        if isinstance(value, str) and key in {
            "as_of",
            "generated_at",
            "source_time",
            "retrieved_at",
        }:
            return datetime.fromisoformat(value)
        return value

    return hashlib.sha256(
        json.dumps(
            normalize(payload | {"content_hash": None}),
            default=str,
            sort_keys=True,
            ensure_ascii=False,
        ).encode()
    ).hexdigest()


def inputs(tmp_path):
    root = tmp_path / "original"
    root.mkdir()
    payload = {
        "schema_version": "1.0",
        "as_of": "2026-10-02T23:00:00+00:00",
        "generated_at": "2026-10-02T23:00:00+00:00",
        "run_id": "daily-2026-10-02",
        "facts": [
            {
                "id": "index.spx.change_percent",
                "metric": "daily_return",
                "instrument": "S&P 500",
                "value": 0.16,
                "previous": None,
                "change": 0.16,
                "unit": "percent",
                "source": "apnews.com",
                "source_url": "https://apnews.com/article/close",
                "source_time": "2026-10-02T20:12:00+00:00",
                "retrieved_at": "2026-10-02T23:00:00+00:00",
                "quality": "reviewed",
                "observation_date": "2026-10-02",
                "retained_vendor_metadata": {"basis": "close"},
            }
        ],
        "events": [],
        "claims": [],
        "sections": [
            {
                "key": "market",
                "title": "Market",
                "facts": ["index.spx.change_percent"],
                "claims": [],
            },
            {"key": "company_news", "title": "公司新闻", "facts": [], "claims": []},
        ],
        "quality_summary": {"status": "degraded"},
        "source_status": {
            "quotes": {"quality": "reviewed", "reason": "source_audited"},
            "research": {"quality": "degraded", "reason": "not_connected"},
            "cross_asset": {"quality": "degraded", "missing_contracts": ["BTC=F"]},
        },
        "missing_sources": ["research", "cross_asset"],
    }
    payload["content_hash"] = _legacy_digest(payload)
    source = root / "daily_report.json"
    source.write_text(dumps_json(payload))
    manifest = root / "publication.json"
    manifest.write_text(
        dumps_json(
            {
                "schema_version": "1.0",
                "publication": "public",
                "report_file": source.name,
                "report_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "content_hash": payload["content_hash"],
                "run_id": payload["run_id"],
            }
        )
    )
    draft = tmp_path / "draft.json"
    draft.write_text(
        dumps_json(
            {
                "market_date": "2026-10-02",
                "candidates": [
                    {
                        "section": "company_news",
                        "title": "Issuer release",
                        "source_url": "https://issuer.test/release",
                        "observation_date": "2026-10-02",
                        "review_status": "needs_review",
                        "phase": "event",
                        "publication_precision": "date",
                        "source_date": "2026-10-02",
                        "source_timezone": "unknown",
                        "time_role": "publication",
                        "usage": "background",
                    }
                ],
            }
        )
    )
    review = tmp_path / "review.json"
    review.write_text(
        dumps_json(
            {
                "market_date": "2026-10-02",
                "draft_sha256": hashlib.sha256(draft.read_bytes()).hexdigest(),
                "reviewer": "independent-audit",
                "decisions": [
                    {
                        "index": 0,
                        "status": "approved",
                        "reason": "Original announcement checked",
                        "approved_summary": "公司披露季度收入增长。",
                        "source_locator": "Revenue paragraph",
                        "verified_facts": ["Quarterly revenue grew"],
                        "display_basis": {
                            "basis": "independent_factual_summary",
                            "scope": "one original factual paragraph",
                            "source_url": "https://issuer.test/release",
                            "verified_on": "2026-10-03",
                        },
                    }
                ],
            }
        )
    )
    return source, manifest, draft, review


def revision(paths, output):
    return import_module("daily_messenger.daily_report.news_revision").revise_news(
        *paths, output, market_date="2026-10-02", news_cutoff=REVISED_AT, revised_at=REVISED_AT
    )


def test_content_digest_matches_legacy_report_hash(tmp_path):
    source, *_ = inputs(tmp_path)
    payload = json.loads(source.read_text())
    digest = import_module("daily_messenger.daily_report.serialization").content_digest
    assert digest(payload) == payload["content_hash"]
    payload["as_of"] = datetime.fromisoformat(payload["as_of"])
    assert digest(payload) == payload["content_hash"]


def test_revision_preserves_all_facts_and_nonresearch_status(tmp_path):
    paths = inputs(tmp_path)
    original_bytes = paths[0].read_bytes()
    before = json.loads(original_bytes)
    result = revision(paths, tmp_path / "stage")
    after = json.loads(result.artifact_path.read_text())
    assert result.changed and result.added_claims == 1
    assert paths[0].read_bytes() == original_bytes
    assert after["facts"] == before["facts"]
    assert after["as_of"] == before["as_of"]
    assert after["generated_at"] == "2026-10-04T01:00:00+00:00"
    assert after["source_status"]["quotes"] == before["source_status"]["quotes"]
    assert after["source_status"]["cross_asset"] == before["source_status"]["cross_asset"]
    assert after["missing_sources"] == ["cross_asset"]
    assert after["quality_summary"]["status"] == "degraded"
    assert after["events"][0]["source_time"] is None
    assert after["quality_summary"]["revision"] == "news_only"
    assert (
        after["quality_summary"]["news_revision"]["input_report_sha256"]
        == hashlib.sha256(original_bytes).hexdigest()
    )
    assert _legacy_digest(after) == after["content_hash"]


def test_repeat_is_noop(tmp_path):
    source, manifest, draft, review = inputs(tmp_path)
    result = revision((source, manifest, draft, review), tmp_path / "first")
    repeated = revision(
        (result.artifact_path, result.artifact_path.parent / "publication.json", draft, review),
        tmp_path / "second",
    )
    assert not repeated.changed
    assert repeated.artifact_path is None
    assert repeated.content_hash == result.content_hash
    assert not (tmp_path / "second").exists()


@pytest.mark.parametrize(
    "fault", ["manifest", "hash", "decisions", "quote", "overlap", "symlink", "existing", "cutoff"]
)
def test_invalid_revision_fails_before_writes(tmp_path, fault):
    paths = inputs(tmp_path)
    output = tmp_path / "stage"
    if fault == "manifest":
        paths[1].write_text("{}")
    elif fault == "hash":
        payload = json.loads(paths[0].read_text())
        payload["facts"][0]["value"] = 99
        paths[0].write_text(dumps_json(payload))
    elif fault in {"decisions", "quote"}:
        payload = json.loads(paths[3].read_text())
        if fault == "decisions":
            payload["decisions"] = []
        else:
            payload["decisions"][0]["ticker"] = "MSFT"
        paths[3].write_text(dumps_json(payload))
    elif fault == "overlap":
        output = paths[0].parent / "nested"
    elif fault == "symlink":
        output.symlink_to(paths[0].parent, target_is_directory=True)
    elif fault == "existing":
        output.mkdir()
        (output / "daily_report.json").write_text("retained")
    before = paths[0].read_bytes()
    with pytest.raises(ValueError):
        if fault == "cutoff":
            import_module("daily_messenger.daily_report.news_revision").revise_news(
                *paths,
                output,
                market_date="2026-10-02",
                news_cutoff=datetime(2026, 10, 5, tzinfo=UTC),
                revised_at=REVISED_AT,
            )
        else:
            revision(paths, output)
    assert paths[0].read_bytes() == before
    if fault not in {"symlink", "existing"}:
        assert not output.exists()
    if fault == "existing":
        assert (output / "daily_report.json").read_text() == "retained"


def test_evidence_identity_conflict_is_rejected(tmp_path):
    paths = inputs(tmp_path)
    first = revision(paths, tmp_path / "first")
    review = json.loads(paths[3].read_text())
    review["decisions"][0]["approved_summary"] = "A different assertion"
    paths[3].write_text(dumps_json(review))
    with pytest.raises(ValueError, match="identity"):
        revision(
            (
                first.artifact_path,
                first.artifact_path.parent / "publication.json",
                paths[2],
                paths[3],
            ),
            tmp_path / "second",
        )
    assert not (tmp_path / "second").exists()


def test_offline_cli_never_loads_credentials_or_fetches(tmp_path, monkeypatch):
    from daily_messenger import cli

    paths = inputs(tmp_path)

    def forbidden(*args, **kwargs):
        raise AssertionError("external side effect during offline revision")

    monkeypatch.setattr(cli, "_load_runtime_env_files", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    for module, name in [
        ("pipeline", "run_daily_report"),
        ("macro", "fetch_us_macro_facts"),
        ("cross_asset", "fetch_cross_asset_facts"),
        ("equity_quotes", "fetch_equity_facts"),
        ("index_quotes", "fetch_index_facts"),
        ("btc_spot", "fetch_btc_spot_facts"),
    ]:
        monkeypatch.setattr(
            import_module(f"daily_messenger.daily_report.{module}"), name, forbidden
        )
    assert (
        cli.main(
            [
                "daily-report",
                "--date",
                "2026-10-02",
                "--revise-news",
                str(paths[0]),
                "--input-manifest",
                str(paths[1]),
                "--reviewed-draft",
                str(paths[2]),
                "--reviewed-decisions",
                str(paths[3]),
                "--out",
                str(tmp_path / "stage"),
            ]
        )
        == 0
    )
    assert (tmp_path / "stage/daily_report.json").is_file()
