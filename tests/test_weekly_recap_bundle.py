"""Synthetic weekly artifacts exercise publication without any external sends."""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import pytest
from PIL import Image

from market_intel_publication.export_site_snapshot import export_site_snapshot
from market_intel_publication.import_reports import import_reports
from market_intel_publication.sync_public_snapshot import sync_snapshot
from market_intel_publication.weekly_recap_bundle import (
    WeeklyInputs,
    export_bundle,
    import_bundle,
    weekly_history,
)
from market_intel_publication.weekly_recap_contract import content_hash, validate_weekly_recap


def bundle(tmp: Path, day: str = "2026-10-23") -> tuple[Path, dict]:
    tmp.mkdir(parents=True, exist_ok=True)
    report = tmp / "source.md"
    report.write_text("# Public weekly facts\n\nSynthetic market/style report.\n")
    image = tmp / "source.png"
    Image.new("RGB", (8, 6), "white").save(image)
    sources = []
    for kind in ("value_regime", "size_style"):
        payload = {
            "schema_version": "research.weekly_analysis.v1",
            "artifact_type": f"{kind}_weekly",
            "as_of": day.replace("-", ""),
            "quality": {"status": "passed", "observation_count": 1},
            "snapshot": {"regime": "NEUTRAL", "streak": 2}
            if kind == "value_regime"
            else {"signal": "small_cap"},
        }
        payload["weekly_features" if kind == "value_regime" else "series"] = (
            [{"date": day.replace("-", ""), "ret_12w": 0.03, "cum": 1.2}]
            if kind == "value_regime"
            else [
                {"date": day.replace("-", ""), "relative_strength": 1.1, "small": 0.2, "large": 0.4}
            ]
        )
        # Private fields remain confined to the admitted owner artifact.
        payload["private_runtime"] = {
            "recipient": "synthetic-private-id",
            "path": "/private/synthetic",
        }
        source = tmp / f"{kind}.json"
        source.write_text(json.dumps(payload))
        sources.append(source)
    output = tmp / "bundle"
    payload = export_bundle(WeeklyInputs(report, image, *sources), day, output, "public")
    assert (
        payload["sources"]["value"]["sha256"] == hashlib.sha256(sources[0].read_bytes()).hexdigest()
    )
    assert "private" not in json.dumps(payload)
    return output, payload


def daily_root(root: Path) -> Path:
    public = root / "artifacts/public"
    (public / "data").mkdir(parents=True)
    (public / "reports").mkdir()
    (public / "data/reports.json").write_text(
        json.dumps({"schema_version": "market_intel_pages.reports.v1", "reports": []})
    )
    (public / "data/daily_summaries.json").write_text(
        json.dumps({"schema_version": "market_intel_pages.daily_summaries.v1", "summaries": []})
    )
    return public


def test_weekly_daily_import_sync_and_snapshot_roundtrip(tmp_path):
    root = tmp_path / "pages"
    public = daily_root(root)
    source, payload = bundle(tmp_path / "input")
    import_bundle(source, root, dry_run=True)
    assert not (public / "data/weekly_recap.json").exists()
    import_bundle(source, root)
    before = {
        p.relative_to(public).as_posix(): p.read_bytes()
        for p in public.rglob("*")
        if p.is_file() and "weekly" in p.name
    }
    report = tmp_path / "daily.md"
    report.write_text(
        "# Morning report\n\n## Overview\n生成时间：2026-10-23 08:00\nMarket opened.\n"
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "market_intel_pages.import.v1",
                "publication": "public",
                "reports": [{"date": "2026-10-23", "kind": "morning", "path": report.name}],
            }
        )
    )
    import_reports(root, manifest, tmp_path / "archive", apply=True)
    sync_snapshot(root, tmp_path / "archive")
    assert all((public / name).read_bytes() == raw for name, raw in before.items())
    export_site_snapshot(root, tmp_path / "snapshot")
    assert all((tmp_path / "snapshot" / name).read_bytes() == raw for name, raw in before.items())
    assert weekly_history(tmp_path / "snapshot") == [payload]


def test_sixth_week_prunes_only_owned_weekly_files(tmp_path):
    root = tmp_path / "pages"
    public = daily_root(root)
    (public / "reports/daily.md").write_text("keep")
    for week in range(6):
        day = (date(2026, 9, 18) + timedelta(weeks=week)).isoformat()
        source, _ = bundle(tmp_path / f"input-{week}", day)
        import_bundle(source, root)
    rows = weekly_history(public)
    assert len(rows) == 5
    assert not (public / "reports/2026-09-18-weekly.md").exists()
    assert not (public / "reports/2026-09-18-weekly.png").exists()
    assert (public / "reports/daily.md").read_text() == "keep"
    with pytest.raises(ValueError, match="stale"):
        import_bundle(tmp_path / "input-0/bundle", root)


@pytest.mark.parametrize(
    "mutation",
    ["extra", "private", "hash", "date", "nan", "duplicate", "path", "enum", "timestamp"],
)
def test_contract_rejects_malformed_public_payloads(tmp_path, mutation):
    _, original = bundle(tmp_path / "input")
    p = copy.deepcopy(original)
    if mutation == "extra":
        p["recipient"] = "private"
    elif mutation == "private":
        p["publication"] = "private"
    elif mutation == "hash":
        p["markdown"] += "changed"
    elif mutation == "date":
        p["series"]["value"][0]["date"] = "2026-10-16"
    elif mutation == "nan":
        p["summary"]["small_crowding"] = float("nan")
    elif mutation == "duplicate":
        p["series"]["size"] *= 2
    elif mutation == "path":
        p["image"]["source_url"] = "../private.png"
    elif mutation == "enum":
        p["summary"]["size_signal"] = "new_unknown"
    elif mutation == "timestamp":
        p["generated_at"] = "2026-10-24T00:00:00"
    if mutation not in {"hash", "nan"}:
        p["content_hash"] = content_hash(p)
    with pytest.raises(ValueError):
        validate_weekly_recap(p)


@pytest.mark.parametrize(
    "file", ["2026-10-23-weekly.md", "2026-10-23-weekly.png", "weekly_recap.json"]
)
def test_bad_bundle_does_not_replace_existing_publication(tmp_path, file):
    root = tmp_path / "pages"
    public = daily_root(root)
    source, _ = bundle(tmp_path / "input")
    import_bundle(source, root)
    before = (public / "data/weekly_recap.json").read_bytes()
    (source / file).write_bytes(b"corrupt")
    with pytest.raises((ValueError, OSError)):
        import_bundle(source, root)
    assert (public / "data/weekly_recap.json").read_bytes() == before


def test_symlink_bundle_and_destination_rejected(tmp_path):
    source, _ = bundle(tmp_path / "input")
    (tmp_path / "linked").symlink_to(source, target_is_directory=True)
    with pytest.raises(ValueError, match="unsafe"):
        import_bundle(tmp_path / "linked", tmp_path / "pages")
    root = tmp_path / "pages"
    public = daily_root(root)
    (public / "data/weekly_recap.json").symlink_to(tmp_path / "outside")
    with pytest.raises(ValueError):
        import_bundle(source, root)
    assert not (tmp_path / "outside").exists()


def test_owner_stale_failed_and_invalid_png_rejected(tmp_path):
    source, _ = bundle(tmp_path / "input")
    base = source.parent
    value = json.loads((base / "value_regime.json").read_text())
    value["quality"]["status"] = "failed"
    (base / "value_regime.json").write_text(json.dumps(value))
    with pytest.raises(ValueError, match="quality"):
        export_bundle(
            WeeklyInputs(
                base / "source.md",
                base / "source.png",
                base / "value_regime.json",
                base / "size_style.json",
            ),
            "2026-10-23",
            tmp_path / "out",
            "public",
        )
    value["quality"]["status"] = "passed"
    value["as_of"] = "20261016"
    (base / "value_regime.json").write_text(json.dumps(value))
    with pytest.raises(ValueError, match="as_of"):
        export_bundle(
            WeeklyInputs(
                base / "source.md",
                base / "source.png",
                base / "value_regime.json",
                base / "size_style.json",
            ),
            "2026-10-23",
            tmp_path / "out",
            "public",
        )


@pytest.mark.parametrize("field", ["value_regime", "size_signal"])
def test_malformed_enum_types_fail_closed(tmp_path, field):
    _, p = bundle(tmp_path / "input")
    p["summary"][field] = []
    with pytest.raises(ValueError):
        validate_weekly_recap(p)


def test_checked_in_public_fixture_matches_json_schema():
    import jsonschema

    from market_intel_publication.weekly_recap_bundle import load_bundle

    root = Path(__file__).resolve().parents[1]
    payload = load_bundle(root / "tests/fixtures/weekly_public")
    schema = json.loads((root / "schemas/public/weekly_recap.schema.json").read_text())
    jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(
        payload
    )


def test_owner_hash_and_facts_use_same_admitted_bytes(tmp_path, monkeypatch):
    from market_intel_publication import weekly_recap_bundle as module

    source, original = bundle(tmp_path / "input")
    base = source.parent
    real_read = module.read_file
    owner = base / "value_regime.json"
    admitted = owner.read_bytes()

    def replace_after_read(path, limit=20_000_000):
        raw = real_read(path, limit)
        if path == owner:
            changed = json.loads(raw)
            changed["weekly_features"][0]["ret_12w"] = 0.9
            path.write_text(json.dumps(changed))
        return raw

    monkeypatch.setattr(module, "read_file", replace_after_read)
    payload = export_bundle(
        WeeklyInputs(base / "source.md", base / "source.png", owner, base / "size_style.json"),
        "2026-10-23",
        tmp_path / "new-bundle",
        "public",
    )
    assert payload["sources"]["value"]["sha256"] == hashlib.sha256(admitted).hexdigest()
    assert payload["series"]["value"] == original["series"]["value"]
