from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from research_contracts import PlatformPublicationArtifact, PlatformPublicationManifest


def _write_json(path: Path, value: object) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    path.write_bytes(content)
    return content


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _briefing(**overrides: object) -> dict:
    paragraphs = [
        {"text": f"合成测试段落 {index}。", "claim_ids": [f"claim-{index}"]}
        for index in range(1, 6)
    ]
    briefing = {
        "schema_version": "market.briefing.v1",
        "market": "US",
        "market_date": "2099-01-02",
        "evidence_cutoff": "2099-01-03T00:00:00Z",
        "generated_at": "2099-01-03T00:00:00Z",
        "run_id": "us-2099-01-02-close-r1",
        "revision": 1,
        "status": "validated_draft",
        "headline": "合成美股收盘简报",
        "paragraphs": paragraphs,
        "brief_text": "\n\n".join(row["text"] for row in paragraphs),
        "thesis": {"stance": "neutral", "confidence": "low", "horizon": "6-12m"},
        "sources": [
            {
                "id": "source-1",
                "title": "Synthetic source",
                "publisher": "Example",
                "url": "https://example.com/synthetic-us-market-briefing",
                "published_at": None,
            }
        ],
        "quality": {
            "structure_passed": True,
            "evidence_links_passed": True,
            "editorial_rules_passed": True,
            "source_audit_passed": False,
            "errors": [],
            "warnings": [],
        },
    }
    briefing.update(overrides)
    return briefing


def _make_bundle(
    root: Path,
    *,
    audience: str = "internal",
    consumer: str = "market-intel",
    briefing_overrides: dict | None = None,
    review_overrides: dict | None = None,
    extra_manifest_artifacts: list[dict] | None = None,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    evidence = {
        "schema_version": "market.evidence.v1",
        "market": "US",
        "market_date": "2099-01-02",
    }
    analysis = {"schema_version": "market.analysis.v1", "claim_count": 5}
    briefing = _briefing(**(briefing_overrides or {}))
    evidence_bytes = _write_json(root / "evidence.json", evidence)
    analysis_bytes = _write_json(root / "analysis.json", analysis)
    briefing_bytes = _write_json(root / "briefing.json", briefing)
    decisions = [
        {"claim_id": f"claim-{index}", "status": "approved", "reason": "Source checked."}
        for index in range(1, 6)
    ]
    review = {
        "schema_version": "market.source-review.v1",
        "market_date": "2099-01-02",
        "reviewer": "synthetic-reviewer",
        "reviewed_at": "2099-01-03T00:01:00Z",
        "hashes": {
            "evidence": _sha256(evidence_bytes),
            "analysis": _sha256(analysis_bytes),
            "briefing": _sha256(briefing_bytes),
        },
        "decisions": decisions,
    }
    review.update(review_overrides or {})
    review_bytes = _write_json(root / "review.json", review)
    artifacts = [
        PlatformPublicationArtifact(
            artifact_id="us-briefing-briefing",
            relative_path="briefing.json",
            schema_version="market.briefing.v1",
            sha256=_sha256(briefing_bytes),
            media_type="application/json",
            audience=audience,
            consumers=(consumer,),
        ),
        PlatformPublicationArtifact(
            artifact_id="us-briefing-review",
            relative_path="review.json",
            schema_version="market.source-review.v1",
            sha256=_sha256(review_bytes),
            media_type="application/json",
            audience=audience,
            consumers=(consumer,),
        ),
    ]
    for index, raw in enumerate(extra_manifest_artifacts or []):
        extra_path = root / str(raw["relative_path"])
        extra_bytes = _write_json(extra_path, {"synthetic_extra": True})
        artifacts.append(
            PlatformPublicationArtifact.from_mapping(
                raw | {"artifact_id": f"extra-{index}", "sha256": _sha256(extra_bytes)}
            )
        )
    manifest = PlatformPublicationManifest(
        generated_at=datetime(2099, 1, 3, tzinfo=UTC),
        producer_repository="quant-market-briefing",
        producer_commit="a" * 40,
        run_id=str(briefing["run_id"]),
        artifacts=tuple(artifacts),
    )
    manifest_path = root / "publication-manifest.json"
    _write_json(manifest_path, manifest.to_mapping())
    return manifest_path


def test_internal_bundle_requires_explicit_opt_in_and_approves_every_claim(tmp_path: Path) -> None:
    from daily_messenger.daily_report.us_market_briefing import load_us_market_briefing_bundle

    manifest_path = _make_bundle(tmp_path / "bundle")

    with pytest.raises(ValueError, match="internal"):
        load_us_market_briefing_bundle(manifest_path)

    bundle = load_us_market_briefing_bundle(manifest_path, allow_internal=True)

    assert bundle.audience == "internal"
    assert bundle.briefing["market_date"] == "2099-01-02"
    assert bundle.run_id == "us-2099-01-02-close-r1"


def test_public_bundle_is_accepted_in_public_mode(tmp_path: Path) -> None:
    from daily_messenger.daily_report.us_market_briefing import load_us_market_briefing_bundle

    manifest_path = _make_bundle(tmp_path / "bundle", audience="public")

    bundle = load_us_market_briefing_bundle(manifest_path)

    assert bundle.audience == "public"


def test_checked_in_synthetic_producer_bundle_is_consumable() -> None:
    from daily_messenger.daily_report.us_market_briefing import load_us_market_briefing_bundle

    manifest_path = (
        Path(__file__).parents[1]
        / "fixtures"
        / "publications"
        / "us_market_briefing"
        / "publication-manifest.json"
    )

    bundle = load_us_market_briefing_bundle(manifest_path, allow_internal=True)

    assert bundle.producer_repository == "quant-market-briefing"
    assert bundle.run_id == "us-2099-01-02-close-r1"


@pytest.mark.parametrize(
    ("briefing_overrides", "error"),
    [
        ({"schema_version": "market.briefing.v2"}, "unsupported"),
        ({"status": "draft"}, "status"),
        ({"market": "CA"}, "schema"),
        ({"extra_field": True}, "schema"),
        (
            {
                "sources": [
                    {
                        "id": "bad",
                        "title": "Bad",
                        "publisher": "Example",
                        "url": "http://example.com",
                        "published_at": None,
                    }
                ]
            },
            "schema",
        ),
        ({"paragraphs": []}, "schema"),
        ({"brief_text": "not the paragraphs"}, "brief_text"),
    ],
)
def test_rejects_invalid_briefing_contract(
    tmp_path: Path, briefing_overrides: dict, error: str
) -> None:
    from daily_messenger.daily_report.us_market_briefing import load_us_market_briefing_bundle

    manifest_path = _make_bundle(
        tmp_path / "bundle", audience="public", briefing_overrides=briefing_overrides
    )

    with pytest.raises(ValueError, match=error):
        load_us_market_briefing_bundle(manifest_path)


@pytest.mark.parametrize(
    "decision_change",
    [
        lambda rows: rows[:-1],
        lambda rows: [*rows, rows[0]],
        lambda rows: [*rows[:1], {**rows[1], "status": "deferred"}, *rows[2:]],
        lambda rows: [*rows[:1], {**rows[1], "claim_id": "extra-claim"}, *rows[2:]],
    ],
    ids=["missing", "duplicate", "deferred", "extra"],
)
def test_rejects_review_without_one_approval_per_final_claim(
    tmp_path: Path, decision_change
) -> None:
    from daily_messenger.daily_report.us_market_briefing import load_us_market_briefing_bundle

    decisions = decision_change(
        [
            {"claim_id": f"claim-{index}", "status": "approved", "reason": "Checked."}
            for index in range(1, 6)
        ]
    )
    manifest_path = _make_bundle(
        tmp_path / "bundle",
        audience="public",
        review_overrides={"decisions": decisions},
    )

    with pytest.raises(ValueError, match="claim|decision"):
        load_us_market_briefing_bundle(manifest_path)


def test_rejects_review_for_different_market_date(tmp_path: Path) -> None:
    from daily_messenger.daily_report.us_market_briefing import load_us_market_briefing_bundle

    manifest_path = _make_bundle(
        tmp_path / "bundle",
        audience="public",
        review_overrides={"market_date": "2099-01-03"},
    )

    with pytest.raises(ValueError, match="date"):
        load_us_market_briefing_bundle(manifest_path)


def test_rejects_review_earlier_than_briefing(tmp_path: Path) -> None:
    from daily_messenger.daily_report.us_market_briefing import load_us_market_briefing_bundle

    manifest_path = _make_bundle(
        tmp_path / "bundle",
        audience="public",
        review_overrides={"reviewed_at": "2099-01-02T23:59:00Z"},
    )

    with pytest.raises(ValueError, match="predates"):
        load_us_market_briefing_bundle(manifest_path)


def test_rejects_manifest_run_id_mismatch(tmp_path: Path) -> None:
    from daily_messenger.daily_report.us_market_briefing import load_us_market_briefing_bundle

    manifest_path = _make_bundle(tmp_path / "bundle", audience="public")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["run_id"] = "different-run"
    _write_json(manifest_path, manifest)

    with pytest.raises(ValueError, match="run_id"):
        load_us_market_briefing_bundle(manifest_path)


def test_rejects_extra_consumer_artifact(tmp_path: Path) -> None:
    from daily_messenger.daily_report.us_market_briefing import load_us_market_briefing_bundle

    manifest_path = _make_bundle(
        tmp_path / "bundle",
        audience="public",
        extra_manifest_artifacts=[
            {
                "relative_path": "extra.json",
                "schema_version": "market.extra.v1",
                "media_type": "application/json",
                "audience": "public",
                "consumers": ["market-intel"],
            }
        ],
    )

    with pytest.raises(ValueError, match="exactly two"):
        load_us_market_briefing_bundle(manifest_path)


def test_rejects_manifest_path_traversal(tmp_path: Path) -> None:
    from daily_messenger.daily_report.us_market_briefing import load_us_market_briefing_bundle

    manifest_path = _make_bundle(tmp_path / "bundle", audience="public")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"][0]["relative_path"] = "../briefing.json"
    _write_json(manifest_path, manifest)

    with pytest.raises(ValueError, match="traversal"):
        load_us_market_briefing_bundle(manifest_path)


def test_rejects_missing_review_file(tmp_path: Path) -> None:
    from daily_messenger.daily_report.us_market_briefing import load_us_market_briefing_bundle

    manifest_path = _make_bundle(tmp_path / "bundle", audience="public")
    (manifest_path.parent / "review.json").unlink()

    with pytest.raises(FileNotFoundError, match="review"):
        load_us_market_briefing_bundle(manifest_path)


def test_rejects_tampered_manifested_briefing(tmp_path: Path) -> None:
    from daily_messenger.daily_report.us_market_briefing import load_us_market_briefing_bundle

    manifest_path = _make_bundle(tmp_path / "bundle", audience="public")
    (manifest_path.parent / "briefing.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="SHA-256"):
        load_us_market_briefing_bundle(manifest_path)


def test_rejects_tampered_unmanifested_evidence(tmp_path: Path) -> None:
    from daily_messenger.daily_report.us_market_briefing import load_us_market_briefing_bundle

    manifest_path = _make_bundle(tmp_path / "bundle", audience="public")
    (manifest_path.parent / "evidence.json").write_text(
        '{"market_date":"2099-01-03"}', encoding="utf-8"
    )

    with pytest.raises(ValueError, match="evidence hash"):
        load_us_market_briefing_bundle(manifest_path)


def test_rejects_tampered_unmanifested_analysis(tmp_path: Path) -> None:
    from daily_messenger.daily_report.us_market_briefing import load_us_market_briefing_bundle

    manifest_path = _make_bundle(tmp_path / "bundle", audience="public")
    (manifest_path.parent / "analysis.json").write_text('{"claim_count":6}', encoding="utf-8")

    with pytest.raises(ValueError, match="analysis hash"):
        load_us_market_briefing_bundle(manifest_path)


def test_rejects_bundle_targeted_at_another_consumer(tmp_path: Path) -> None:
    from daily_messenger.daily_report.us_market_briefing import load_us_market_briefing_bundle

    manifest_path = _make_bundle(tmp_path / "bundle", audience="public", consumer="other-consumer")

    with pytest.raises(ValueError, match="consumer|artifact"):
        load_us_market_briefing_bundle(manifest_path)


def test_rejects_evidence_symlink_escaping_bundle(tmp_path: Path) -> None:
    from daily_messenger.daily_report.us_market_briefing import load_us_market_briefing_bundle

    manifest_path = _make_bundle(tmp_path / "bundle", audience="public")
    bundle_root = manifest_path.parent
    outside = tmp_path / "outside-evidence.json"
    outside.write_bytes((bundle_root / "evidence.json").read_bytes())
    (bundle_root / "evidence.json").unlink()
    try:
        (bundle_root / "evidence.json").symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")

    with pytest.raises(ValueError, match="escapes bundle"):
        load_us_market_briefing_bundle(manifest_path)
