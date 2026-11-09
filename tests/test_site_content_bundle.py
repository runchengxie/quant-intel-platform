"""Synthetic transport tests; installed VCS acceptance is a separate release gate."""

import hashlib
import importlib
import importlib.util
import json
import stat
import zipfile
from dataclasses import asdict

import pytest

from market_intel_publication.asia_news_contract import build_public_asia_news
from market_intel_publication.export_site_snapshot import export_site_snapshot
from market_intel_publication.weekly_recap_bundle import import_bundle
from tests._site_content_test_utils import (
    CREATED,
    REVISION,
    all_families,
    api,
    historical_source,
    installed_fixture,
    pack,
    review_candidate,
    rewrite,
    verify,
    write,
)
from tests.test_weekly_recap_bundle import bundle, daily_root


def test_deterministic_bundle_roundtrip_all_families(tmp_path, monkeypatch):
    codec = api(monkeypatch)
    root = all_families(tmp_path)
    # Source history and unrelated private inputs never become payload members.
    (root / "artifacts/public/reports/old-secret.md").write_text("PRIVATE")
    (root / "private.env").write_text("PRIVATE")
    first, second = tmp_path / "first.zip", tmp_path / "second.zip"
    receipt = pack(codec, root, first)
    assert pack(codec, root, second) == receipt
    assert first.read_bytes() == second.read_bytes()
    assert receipt.archive_sha256 == hashlib.sha256(first.read_bytes()).hexdigest()
    assert receipt.archive_sha256 != receipt.bundle_id
    output = tmp_path / "unpacked"
    assert verify(codec, first, output) == receipt
    public = output / "artifacts/public"
    assert not (public / "reports/old-secret.md").exists()
    for record in receipt.files:
        raw = (public / record.path).read_bytes()
        assert len(raw) == record.bytes
        assert hashlib.sha256(raw).hexdigest() == record.sha256
    export_site_snapshot(output, tmp_path / "reexport")
    for name in ("reports", "market_daily_reports", "weekly_recaps"):
        rows = json.loads((tmp_path / "reexport/data" / f"{name}.json").read_text())["reports"]
        assert len(rows) == 5
    assert len(list((tmp_path / "reexport/data/asia_news").glob("*.json"))) == 5
    assert len(list((tmp_path / "reexport/data/charts").glob("*.json"))) == 5
    assert len(json.loads((tmp_path / "reexport/data/insights.json").read_text())["insights"]) == 1
    assert (
        len(json.loads((tmp_path / "reexport/data/daily_summaries.json").read_text())["summaries"])
        == 1
    )
    for record in receipt.files:
        if record.path.startswith("data/asia_news/"):
            assert json.loads((tmp_path / "reexport" / record.path).read_bytes()) == json.loads(
                (public / record.path).read_bytes()
            )
        elif record.path != "data/health.json":
            assert (tmp_path / "reexport" / record.path).read_bytes() == (
                public / record.path
            ).read_bytes()
    assert asdict(receipt)["schema_version"] == "market_intel.site_content_receipt.v1"


@pytest.mark.parametrize(
    "mutation", ["private", "unknown", "nested", "missing_public", "duplicate_json", "symlink"]
)
def test_pack_rejects_nonpublic_indexed_input(tmp_path, monkeypatch, mutation):
    codec = api(monkeypatch)
    root = all_families(tmp_path)
    path = root / "artifacts/public/data/market_daily_report.json"
    value = json.loads(path.read_text())
    if mutation == "private":
        value["publication"] = "private"
    elif mutation == "unknown":
        value["private_receipt"] = {"recipient": "private"}
    elif mutation == "nested":
        value["quality_summary"]["private_token"] = "private"
    elif mutation == "missing_public":
        value.pop("publication")
    elif mutation == "duplicate_json":
        path.write_text('{"schema_version":"1.0","schema_version":"1.1"}')
    elif mutation == "symlink":
        path.unlink()
        path.symlink_to(root / "artifacts/public/data/market_daily_reports.json")
    if mutation not in {"duplicate_json", "symlink"}:
        write(path, value)
        history = root / "artifacts/public/data/market_daily_reports.json"
        data = json.loads(history.read_text())
        data["reports"][0] = value
        write(history, data)
    output = tmp_path / "bad.zip"
    with pytest.raises(ValueError):
        pack(codec, root, output)
    assert not output.exists()


@pytest.mark.parametrize(
    "mutation",
    [
        "digest",
        "size",
        "producer",
        "unknown",
        "duplicate_json",
        "duplicate_zip",
        "traversal",
        "backslash",
        "drive",
        "symlink",
        "device",
        "extra",
        "timestamp",
    ],
)
def test_verify_rejects_malformed_bundle_without_output(tmp_path, monkeypatch, mutation):
    codec = api(monkeypatch)
    root = tmp_path / "source"
    daily_root(root)
    good, bad = tmp_path / "good.zip", tmp_path / "bad.zip"
    pack(codec, root, good)

    def change(entries):  # noqa: PLR0912 - explicit independent hostile mutations
        info, raw = entries[0]
        manifest = json.loads(raw)
        if mutation in {"digest", "size", "producer", "unknown", "duplicate_json"}:
            if mutation == "digest":
                manifest["files"][0]["sha256"] = "f" * 64
            elif mutation == "size":
                manifest["files"][0]["bytes"] += 1
            elif mutation == "producer":
                manifest["producer"]["source_sha256"] = "f" * 64
            elif mutation == "unknown":
                manifest["private"] = "secret"
            raw = json.dumps(manifest).encode()
            if mutation == "duplicate_json":
                raw = raw[:-1] + b',"publication":"public"}'
            entries[0] = (info, raw)
        elif mutation == "duplicate_zip":
            entries.append(entries[1])
        elif mutation == "extra":
            extra = zipfile.ZipInfo("payload/data/private.json")
            entries.append((extra, b"{}"))
        else:
            info, raw = entries[1]
            if mutation == "traversal":
                info.filename = "payload/../secret"
            elif mutation == "backslash":
                info.filename = "payload\\data\\secret"
            elif mutation == "drive":
                info.filename = "C:/secret"
            elif mutation == "timestamp":
                info.date_time = (2020, 1, 1, 0, 0, 0)
            else:
                mode = stat.S_IFLNK if mutation == "symlink" else stat.S_IFCHR
                info.create_system = 3
                info.external_attr = (mode | 0o644) << 16
            entries[1] = (info, raw)

    if mutation == "duplicate_zip":
        with pytest.warns(UserWarning, match="Duplicate name"):
            rewrite(good, bad, change)
    else:
        rewrite(good, bad, change)
    output = tmp_path / "output"
    with pytest.raises(ValueError):
        verify(codec, bad, output)
    assert not output.exists()


def test_outputs_and_inputs_never_overlap_or_replace(tmp_path, monkeypatch):
    codec = api(monkeypatch)
    root = tmp_path / "source"
    daily_root(root)
    with pytest.raises(ValueError):
        pack(codec, root, root / "bad.zip")
    archive = tmp_path / "bundle.zip"
    pack(codec, root, archive)
    before = archive.read_bytes()
    with pytest.raises(ValueError):
        pack(codec, root, archive)
    with pytest.raises(ValueError):
        verify(codec, archive, tmp_path)
    assert archive.read_bytes() == before
    with pytest.raises(ValueError):
        codec.verify_site_content(
            archive, "f" * 64, tmp_path / "wrong", expected_producer_revision=REVISION
        )
    assert not (tmp_path / "wrong").exists()


@pytest.mark.parametrize(
    "limit",
    [
        "MAX_ARCHIVE_BYTES",
        "MAX_EXPANDED_BYTES",
        "MAX_FILE_BYTES",
        "MAX_FILES",
        "MAX_MANIFEST_BYTES",
    ],
)
def test_limits_fail_before_promoting(tmp_path, monkeypatch, limit):
    codec = api(monkeypatch)
    contract = importlib.import_module("market_intel_publication.site_content_contract")
    root = tmp_path / "source"
    daily_root(root)
    good = tmp_path / "good.zip"
    pack(codec, root, good)
    monkeypatch.setattr(contract, limit, 1)
    with pytest.raises(ValueError):
        verify(codec, good, tmp_path / "rejected")
    assert not (tmp_path / "rejected").exists()
    with pytest.raises(ValueError):
        pack(codec, root, tmp_path / "rejected.zip")
    assert not (tmp_path / "rejected.zip").exists()


def test_uninstalled_producer_identity_is_not_caller_asserted(monkeypatch):
    from market_intel_publication import site_content_contract as contract

    class Editable:
        def read_text(self, name):
            return json.dumps({"url": "file:///synthetic", "dir_info": {"editable": True}})

    monkeypatch.setattr(contract.metadata, "distribution", lambda name: Editable())
    with pytest.raises(ValueError, match="immutable VCS"):
        contract.installed_producer(REVISION)


def test_cli_receipt_is_bound_and_failures_preserve_outputs(tmp_path, monkeypatch):
    api(monkeypatch)
    assert importlib.util.find_spec("market_intel_publication.site_content_cli") is not None
    cli = importlib.import_module("market_intel_publication.site_content_cli")
    root = tmp_path / "source"
    daily_root(root)
    archive, receipt_path = tmp_path / "bundle.zip", tmp_path / "pack.json"
    cli.pack_main(
        [
            "--root",
            str(root),
            "--output",
            str(archive),
            "--created-at",
            CREATED,
            "--producer-revision",
            REVISION,
            "--receipt",
            str(receipt_path),
        ]
    )
    receipt = json.loads(receipt_path.read_text())
    assert receipt["archive_sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest()
    output, verify_receipt = tmp_path / "verified", tmp_path / "verify.json"
    cli.verify_main(
        [
            "--bundle",
            str(archive),
            "--sha256",
            receipt["archive_sha256"],
            "--output",
            str(output),
            "--expected-producer-revision",
            REVISION,
            "--receipt",
            str(verify_receipt),
        ]
    )
    assert json.loads(verify_receipt.read_text()) == receipt
    previous = archive.read_bytes(), receipt_path.read_bytes()
    with pytest.raises(SystemExit):
        cli.pack_main(
            [
                "--root",
                str(root),
                "--output",
                str(archive),
                "--created-at",
                CREATED,
                "--producer-revision",
                REVISION,
                "--receipt",
                str(receipt_path),
            ]
        )
    assert previous == (archive.read_bytes(), receipt_path.read_bytes())
    with pytest.raises(SystemExit):
        cli.verify_main(
            [
                "--bundle",
                str(archive),
                "--sha256",
                "f" * 64,
                "--output",
                str(tmp_path / "bad-output"),
                "--expected-producer-revision",
                REVISION,
                "--receipt",
                str(tmp_path / "bad-receipt.json"),
            ]
        )
    assert not (tmp_path / "bad-output").exists()
    assert not (tmp_path / "bad-receipt.json").exists()


@pytest.mark.parametrize("metadata", ["treasury_revision", "reviewed_movers", "diagnostics"])
def test_owner_metadata_variants_are_preserved(tmp_path, monkeypatch, metadata):
    codec = api(monkeypatch)
    root = all_families(tmp_path)
    public = root / "artifacts/public"
    if metadata == "diagnostics":
        write(
            public / "data/insights.json",
            {
                "schema_version": "market_intel_pages.insights.v1",
                "generation": {
                    "status": "unavailable",
                    "diagnostics": {
                        "http_status": 429,
                        "api_status": 1008,
                        "reason": "rate_limit",
                        "category": "rate_limit",
                    },
                },
                "insights": [],
                "outcomes": [],
            },
        )
    else:
        path = public / "data/market_daily_reports.json"
        history = json.loads(path.read_text())
        row = history["reports"][0]
        if metadata == "treasury_revision":
            row["quality_summary"]["treasury_revision"] = {
                "schema_version": "market_intel.treasury_revision.v1",
                "parent_content_hash": "c" * 64,
                "original_as_of": row["as_of"],
                "revised_at": row["generated_at"],
                "expected_observation_date": "2026-10-23",
            }
        else:
            row["source_status"]["equities"] = {
                "quality": "ok",
                "reviewed_movers": [{"ticker": "TEST", "evidence_id": "news.test"}],
            }
        write(path, history)
        write(public / "data/market_daily_report.json", row)
    receipt = pack(codec, root, tmp_path / "bundle.zip")
    assert receipt.files


def test_legacy_public_formats_absent_remains_supported(tmp_path, monkeypatch):
    codec = api(monkeypatch)
    root = all_families(tmp_path)
    public = root / "artifacts/public"
    history = json.loads((public / "data/market_daily_reports.json").read_text())
    for row in history["reports"]:
        row.pop("report_formats")
    write(public / "data/market_daily_reports.json", history)
    write(public / "data/market_daily_report.json", history["reports"][0])
    assert pack(codec, root, tmp_path / "legacy.zip").files


@pytest.mark.parametrize("malformed", ["unknown_field", "unindexed", "duplicate_json"])
def test_valid_transport_hashes_never_grant_public_eligibility(tmp_path, monkeypatch, malformed):
    codec = api(monkeypatch)
    from market_intel_publication import site_content_contract as contract

    root = tmp_path / "source"
    daily_root(root)
    archive = tmp_path / "good.zip"
    pack(codec, root, archive)
    with zipfile.ZipFile(archive) as original:
        manifest = json.loads(original.read("manifest.json"))
        payload = {
            row["path"]: original.read("payload/" + row["path"]) for row in manifest["files"]
        }
    if malformed == "unindexed":
        payload["data/private.json"] = b'{"secret":"private"}'
    elif malformed == "duplicate_json":
        payload["data/reports.json"] = (
            b'{"schema_version":"market_intel_pages.reports.v1","reports":[],"reports":[]}'
        )
    else:
        data = json.loads(payload["data/reports.json"])
        data["private_receipt"] = "private"
        payload["data/reports.json"] = contract.canonical(data)
    changed = codec._manifest(payload, CREATED, manifest["producer"])
    bad = tmp_path / "bad.zip"
    bad.write_bytes(codec._archive(changed, payload))
    with pytest.raises(ValueError):
        verify(codec, bad, tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_cli_rolls_back_receipt_when_output_promotion_fails(tmp_path, monkeypatch):
    api(monkeypatch)
    from pathlib import Path

    from market_intel_publication.site_content_cli import pack_main

    root = tmp_path / "source"
    daily_root(root)
    output, receipt = tmp_path / "bundle.zip", tmp_path / "receipt.json"
    original = Path.hardlink_to

    def fail_output(path, target):
        if path == output:
            raise OSError("synthetic promotion failure")
        return original(path, target)

    monkeypatch.setattr(Path, "hardlink_to", fail_output)
    with pytest.raises(SystemExit):
        pack_main(
            [
                "--root",
                str(root),
                "--output",
                str(output),
                "--created-at",
                CREATED,
                "--producer-revision",
                REVISION,
                "--receipt",
                str(receipt),
            ]
        )
    assert not output.exists()
    assert not receipt.exists()


def test_pack_revalidates_exported_payload_before_archive(tmp_path, monkeypatch):
    codec = api(monkeypatch)
    original = codec.export_site_snapshot

    def injected(root, output):
        original(root, output)
        (output / "data/unindexed.json").write_text('{"private":"secret"}')

    monkeypatch.setattr(codec, "export_site_snapshot", injected)
    root = tmp_path / "source"
    daily_root(root)
    with pytest.raises(ValueError, match="unindexed"):
        pack(codec, root, tmp_path / "output.zip")
    assert not (tmp_path / "output.zip").exists()


def test_nested_object_in_public_scalar_field_cannot_escape(tmp_path, monkeypatch):
    codec = api(monkeypatch)
    root = all_families(tmp_path)
    public = root / "artifacts/public"
    history = json.loads((public / "data/market_daily_reports.json").read_text())
    history["reports"][0]["as_of"] = {"private_path": "/private"}
    write(public / "data/market_daily_reports.json", history)
    write(public / "data/market_daily_report.json", history["reports"][0])
    with pytest.raises(ValueError):
        pack(codec, root, tmp_path / "bad.zip")
    assert not (tmp_path / "bad.zip").exists()


def test_verified_snapshot_accepts_family_updates_and_rebuilds_only_derived_sidecars(
    tmp_path, monkeypatch
):
    codec = api(monkeypatch)
    from daily_messenger.daily_report.serialization import content_digest
    from market_intel_publication.import_market_daily_report import import_report
    from market_intel_publication.import_reports import import_reports

    root = all_families(tmp_path)
    archive = tmp_path / "initial.zip"
    pack(codec, root, archive)
    candidate = tmp_path / "candidate"
    verify(codec, archive, candidate)
    public = candidate / "artifacts/public"
    for name in ("health", "us_daily_status"):
        payload = json.loads((public / f"data/{name}.json").read_text())
        payload["private_stale_state"] = {"recipient": "private"}
        write(public / f"data/{name}.json", payload)
    raw = {
        "schema_version": "1.0",
        "as_of": "2026-10-26T20:00:00Z",
        "generated_at": "2026-10-26T21:00:00Z",
        "run_id": "daily-2026-10-26",
        "facts": [],
        "claims": [],
        "events": [],
        "sections": [],
        "source_status": {},
    }
    raw["content_hash"] = content_digest(raw)
    source = tmp_path / "daily_report.json"
    write(source, raw)
    public_manifest = tmp_path / "daily_manifest.json"
    write(
        public_manifest,
        {
            "schema_version": "1.0",
            "publication": "public",
            "report_file": source.name,
            "run_id": raw["run_id"],
            "content_hash": raw["content_hash"],
            "report_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        },
    )
    import_report(source, candidate, public_manifest)
    markdown = tmp_path / "asia.md"
    markdown.write_text(
        "# Public Asia\n\n## Market\n生成时间：2026-10-26 20:00\nNew public facts.\n"
    )
    asia_manifest = tmp_path / "asia_manifest.json"
    write(
        asia_manifest,
        {
            "schema_version": "market_intel_pages.import.v1",
            "publication": "public",
            "reports": [{"date": "2026-10-26", "kind": "evening", "path": markdown.name}],
        },
    )
    import_reports(candidate, asia_manifest, tmp_path / "archive", apply=True)
    weekly, _ = bundle(tmp_path / "next-weekly", "2026-10-30")
    import_bundle(weekly, candidate)
    next_archive = tmp_path / "next.zip"
    pack(codec, candidate, next_archive)
    final = tmp_path / "final"
    verify(codec, next_archive, final)
    final_public = final / "artifacts/public"
    assert (
        json.loads((final_public / "data/reports.json").read_text())["reports"][-1]["date"]
        == "2026-10-26"
    )
    assert (
        json.loads((final_public / "data/market_daily_report.json").read_text())["run_id"]
        == "daily-2026-10-26"
    )
    assert json.loads((final_public / "data/weekly_recap.json").read_text())["date"] == "2026-10-30"
    for name in ("health", "us_daily_status"):
        assert "private" not in (final_public / f"data/{name}.json").read_text()


def test_same_date_asia_revision_filters_stale_commentary_without_losing_other_families(
    tmp_path, monkeypatch
):
    codec = api(monkeypatch)
    from market_intel_publication.import_reports import import_reports

    root = all_families(tmp_path)
    first = tmp_path / "first.zip"
    pack(codec, root, first)
    candidate = tmp_path / "candidate"
    verify(codec, first, candidate)
    text = (
        "# Revised public report\n\n## Market\n生成时间：2026-10-23 21:00\nRevised public facts.\n"
    )
    source = tmp_path / "revised.md"
    source.write_text(text)
    news = build_public_asia_news(
        [],
        report_date="2026-10-23",
        generated_at="2026-10-23T21:30:00+08:00",
        report_sha256=hashlib.sha256(text.encode()).hexdigest(),
    )
    write(tmp_path / "news.json", news)
    manifest = tmp_path / "import.json"
    write(
        manifest,
        {
            "schema_version": "market_intel_pages.import.v1",
            "publication": "public",
            "reports": [
                {
                    "date": "2026-10-23",
                    "kind": "evening",
                    "path": source.name,
                    "asia_news_path": "news.json",
                }
            ],
        },
    )
    import_reports(candidate, manifest, tmp_path / "archive", apply=True)
    revised = tmp_path / "revised.zip"
    pack(codec, candidate, revised)
    result = tmp_path / "result"
    verify(codec, revised, result)
    public = result / "artifacts/public"
    assert json.loads((public / "data/daily_summaries.json").read_text())["summaries"] == []
    assert json.loads((public / "data/insights.json").read_text())["insights"] == []
    assert (public / "reports/2026-10-23-evening.md").read_text() == text
    assert len(json.loads((public / "data/market_daily_reports.json").read_text())["reports"]) == 5
    assert len(json.loads((public / "data/weekly_recaps.json").read_text())["reports"]) == 5


def test_installed_producer_rejects_tampered_record_bytes(tmp_path, monkeypatch):
    contract, _ = installed_fixture(tmp_path, monkeypatch, raw=b"tampered")
    with pytest.raises(ValueError, match="RECORD hash"):
        contract.installed_producer(REVISION)


def test_candidate_clock_is_bound_even_with_valid_archive_hash(tmp_path, monkeypatch):
    codec = api(monkeypatch)
    root = tmp_path / "source"
    daily_root(root)
    archive = tmp_path / "first.zip"
    pack(codec, root, archive)
    with zipfile.ZipFile(archive) as source:
        manifest = json.loads(source.read("manifest.json"))
        payload = {row["path"]: source.read("payload/" + row["path"]) for row in manifest["files"]}
    manifest = codec._manifest(payload, "2026-11-02T00:00:00Z", manifest["producer"])
    bad = tmp_path / "clock.zip"
    bad.write_bytes(codec._archive(manifest, payload))
    with pytest.raises(ValueError, match="clock"):
        verify(codec, bad, tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_producer_rejects_unrecorded_package_files(tmp_path, monkeypatch):
    contract, module = installed_fixture(tmp_path, monkeypatch)
    (module.parent / "injected.py").write_bytes(b"unrecorded")
    with pytest.raises(ValueError, match="unrecorded"):
        contract.installed_producer(REVISION)


@pytest.mark.parametrize(
    "stamp",
    [
        "20261101T000000Z",
        "2026-11-01 00:00:00Z",
        "2026-11-01T00:00:00+08:00",
        "2026-11-01T00:00:00",
    ],
)
def test_creation_time_requires_explicit_rfc3339_utc(tmp_path, monkeypatch, stamp):
    codec = api(monkeypatch)
    root = tmp_path / "source"
    daily_root(root)
    with pytest.raises(ValueError, match="UTC"):
        codec.pack_site_content(
            root, tmp_path / "bad.zip", created_at_utc=stamp, producer_revision=REVISION
        )
    assert not (tmp_path / "bad.zip").exists()


def test_installed_cache_hardlinks_are_measured_but_payload_hardlinks_are_rejected(
    tmp_path, monkeypatch
):
    contract, module = installed_fixture(tmp_path, monkeypatch)
    (tmp_path / "cache.py").hardlink_to(module)
    assert contract.installed_producer(REVISION)["source_revision"] == REVISION
    with pytest.raises(ValueError, match="regular file"):
        contract.source_file(module, module.parent)


def test_published_json_schema_matches_real_manifest(tmp_path, monkeypatch):
    from pathlib import Path

    import jsonschema

    codec = api(monkeypatch)
    root = tmp_path / "source"
    daily_root(root)
    archive = tmp_path / "bundle.zip"
    pack(codec, root, archive)
    schema = json.loads(
        (
            Path(__file__).parents[1] / "schemas/public/site_content_bundle.v1.schema.json"
        ).read_text()
    )
    jsonschema.Draft202012Validator.check_schema(schema)
    with zipfile.ZipFile(archive) as source:
        manifest = json.loads(source.read("manifest.json"))
    jsonschema.validate(manifest, schema)
    manifest["unknown"] = "private"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(manifest, schema)


def test_pack_is_deterministic_across_hash_seed_processes(tmp_path):
    """Synthetic provenance stub isolates serialization; VCS CLI proof is external."""
    import os
    import subprocess
    import sys

    root = all_families(tmp_path)
    script = """
import sys
from pathlib import Path
from market_intel_publication import site_content_codec as codec
codec.installed_producer = lambda revision: {
    "owner": "quant-intel-platform", "distribution": "market-intel",
    "source_revision": revision, "source_sha256": "b" * 64,
}
codec.pack_site_content(Path(sys.argv[1]), Path(sys.argv[2]),
    created_at_utc="2026-11-01T00:00:00Z", producer_revision="a" * 40)
"""
    outputs = []
    for seed in ("1", "2"):
        output = tmp_path / f"seed-{seed}.zip"
        subprocess.run(
            [sys.executable, "-c", script, str(root), str(output)],
            check=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
            cwd=tmp_path,
        )
        outputs.append(output.read_bytes())
    assert outputs[0] == outputs[1]


@pytest.mark.parametrize("operation", ["pack", "verify"])
@pytest.mark.parametrize(
    "mutation",
    [
        ("section.paragraphs", "Malformed paragraphs scalar"),
        ("section.paragraphs", ["Valid text", 7]),
        ("section.paragraphs", ["Valid text", None]),
        ("section.title", 7),
        ("section.title", ["Wrong list"]),
        ("title", 7),
        ("title", ["Wrong list"]),
        ("summary", False),
        ("generation_mode", ["backfill"]),
        ("generated_at", False),
        ("source_hash", "f" * 64),
    ],
)
def test_reviewed_public_contract_rejects_wrong_shapes_and_aggregate_hash(
    tmp_path, monkeypatch, capsys, mutation, operation
):
    codec = api(monkeypatch)
    command, args, output, receipt = review_candidate(tmp_path, codec, mutation, operation)
    with pytest.raises(SystemExit) as error:
        command(args)
    assert error.value.code == 2
    assert not output.exists()
    assert not receipt.exists()
    expected = "aggregate" if mutation[0] == "source_hash" else "string"
    assert expected in capsys.readouterr().err


@pytest.mark.parametrize("hash_map", ["present", "empty", "absent"])
def test_historical_asia_shapes_and_insight_source_forms_roundtrip(tmp_path, monkeypatch, hash_map):
    codec = api(monkeypatch)
    root, expected = historical_source(tmp_path, hash_map)
    archive = tmp_path / "historical.zip"
    pack(codec, root, archive)
    output = tmp_path / "verified"
    verify(codec, archive, output)
    public = output / "artifacts/public"
    rows = json.loads((public / "data/reports.json").read_bytes())["reports"]
    assert {row["kind"] for row in rows} == {"morning", "evening"}
    assert rows[0]["sections"][-1] == {"title": "", "paragraphs": []}
    assert rows[0]["generation_mode"] == "backfill"
    assert (
        json.loads((public / "data/insights.json").read_bytes())["insights"][0]["source_hash"]
        == expected
    )


def test_stale_insight_is_filtered_before_new_aggregate_binding(tmp_path, monkeypatch):
    codec = api(monkeypatch)
    root = all_families(tmp_path)
    path = root / "artifacts/public/data/insights.json"
    payload = json.loads(path.read_bytes())
    note = payload["insights"][0]
    note["source_hash"] = "f" * 64
    note["source_hashes"][note["morning_report_id"]] = "e" * 64
    write(path, payload)
    archive = tmp_path / "stale.zip"
    pack(codec, root, archive)
    verify(codec, archive, tmp_path / "verified")
    assert (
        json.loads((tmp_path / "verified/artifacts/public/data/insights.json").read_bytes())[
            "insights"
        ]
        == []
    )
