"""Preview and apply are separate, and prior public revisions remain archived."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.chart_review import make_review_template
from scripts.import_charts import import_charts
from tests.test_chart_contract import public_chart, rehash


@pytest.fixture
def site_root(tmp_path: Path) -> Path:
    root = tmp_path / "site"
    (root / "artifacts/public/data").mkdir(parents=True)
    (root / "artifacts/public/data/reports.json").write_text(
        json.dumps(
            {
                "schema_version": "market_intel_pages.reports.v1",
                "reports": [{"id": "2026-09-18-morning", "date": "2026-09-18", "kind": "morning"}],
            }
        ),
        encoding="utf-8",
    )
    return root


@pytest.fixture
def public_chart_path(tmp_path: Path) -> Path:
    path = tmp_path / "input.json"
    path.write_text(json.dumps(public_chart()), encoding="utf-8")
    return path


@pytest.fixture
def review_path(tmp_path: Path, public_chart_path: Path) -> Path:
    path = tmp_path / "private-review.json"
    review = make_review_template(json.loads(public_chart_path.read_text(encoding="utf-8")))
    review["reviewer"] = "research-editor"
    review["reviewed_at"] = "2026-09-19T08:00:00+08:00"
    for point in review["points"]:
        point.update(
            fact_url="https://example.test/dated-values",
            fact_note="已核对观测日、单位及数值",
            rights_url="https://example.test/data-license",
            rights_note="已核对公开再展示的许可依据",
        )
    path.write_text(json.dumps(review), encoding="utf-8")
    return path


def test_preview_does_not_write(site_root: Path, public_chart_path: Path, review_path: Path, tmp_path: Path):
    archive = tmp_path / "archive"
    result = import_charts(site_root, public_chart_path, archive, review=review_path)
    assert result == {"changed": 1, "report_id": "2026-09-18-morning", "applied": False}
    assert not (site_root / "artifacts/public/data/charts/2026-09-18-morning.json").exists()
    assert not archive.exists()


def test_apply_archives_prior_version_and_is_idempotent(
    site_root: Path, public_chart_path: Path, review_path: Path, tmp_path: Path
):
    archive = tmp_path / "archive"
    first = import_charts(site_root, public_chart_path, archive, review=review_path, apply=True)
    assert first["applied"] is True
    assert (site_root / "artifacts/public/data/charts/2026-09-18-morning.json").is_file()
    destination = site_root / "artifacts/public/data/charts/2026-09-18-morning.json"
    old = destination.read_bytes()
    assert (
        import_charts(site_root, public_chart_path, archive, review=review_path, apply=True)["changed"] == 0
    )
    revised = public_chart()
    revised["charts"][0]["points"][0]["value"] = 110.0
    public_chart_path.write_text(json.dumps(rehash(revised)), encoding="utf-8")
    revised_review = make_review_template(json.loads(public_chart_path.read_text(encoding="utf-8")))
    revised_review["reviewer"] = "research-editor"
    revised_review["reviewed_at"] = "2026-09-19T09:00:00+08:00"
    for point in revised_review["points"]:
        point.update(
            fact_url="https://example.test/dated-values",
            fact_note="已核对新数值",
            rights_url="https://example.test/data-license",
            rights_note="已核对公开许可",
        )
    review_path.write_text(json.dumps(revised_review), encoding="utf-8")
    assert (
        import_charts(site_root, public_chart_path, archive, review=review_path, apply=True)["changed"] == 1
    )
    assert destination.read_bytes() != old
    assert any(path.read_bytes() == old for path in archive.rglob("*.json"))
    assert len(list((archive / "chart_reviews" / "2026-09-18-morning").rglob("*.json"))) == 2


def test_new_review_is_archived_even_when_chart_is_unchanged(
    site_root: Path, public_chart_path: Path, review_path: Path, tmp_path: Path
):
    archive = tmp_path / "archive"
    assert (
        import_charts(site_root, public_chart_path, archive, review=review_path, apply=True)["changed"] == 1
    )
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["reviewed_at"] = "2026-09-20T09:00:00+08:00"
    review["points"][0]["fact_note"] = "再次核对数值与观测日"
    review_path.write_text(json.dumps(review), encoding="utf-8")
    result = import_charts(site_root, public_chart_path, archive, review=review_path, apply=True)
    assert result["changed"] == 0
    receipts = list((archive / "chart_reviews" / "2026-09-18-morning").rglob("*.json"))
    assert len(receipts) == 2
    assert {json.loads(path.read_text(encoding="utf-8"))["reviewed_at"] for path in receipts} == {
        "2026-09-19T08:00:00+08:00",
        "2026-09-20T09:00:00+08:00",
    }


def test_candidate_and_wrong_report_are_rejected(
    site_root: Path, public_chart_path: Path, review_path: Path, tmp_path: Path
):
    candidate = public_chart()
    candidate["publication"] = "candidate"
    public_chart_path.write_text(json.dumps(rehash(candidate)), encoding="utf-8")
    with pytest.raises(ValueError, match="public"):
        import_charts(site_root, public_chart_path, tmp_path / "archive", review=review_path, apply=True)
    assert not (site_root / "artifacts/public/data/charts").exists()


def test_public_hash_alone_cannot_bypass_review(site_root: Path, public_chart_path: Path, tmp_path: Path):
    with pytest.raises(ValueError, match="review receipt"):
        import_charts(site_root, public_chart_path, tmp_path / "archive", apply=True)


def test_review_must_match_every_point(
    site_root: Path, public_chart_path: Path, review_path: Path, tmp_path: Path
):
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["points"][0]["fact_url"] = ""
    review_path.write_text(json.dumps(review), encoding="utf-8")
    with pytest.raises(ValueError, match="fact_url"):
        import_charts(site_root, public_chart_path, tmp_path / "archive", review=review_path, apply=True)


def test_review_hash_and_coverage_are_binding(
    site_root: Path, public_chart_path: Path, review_path: Path, tmp_path: Path
):
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["points"] = []
    review_path.write_text(json.dumps(review), encoding="utf-8")
    with pytest.raises(ValueError, match="every chart point"):
        import_charts(site_root, public_chart_path, tmp_path / "archive", review=review_path)
    review["chart_sha256"] = "0" * 64
    review_path.write_text(json.dumps(review), encoding="utf-8")
    with pytest.raises(ValueError, match="chart hash"):
        import_charts(site_root, public_chart_path, tmp_path / "archive", review=review_path)


def test_review_template_cli_refuses_public_repo_output(public_chart_path: Path):
    root = Path(__file__).resolve().parents[1]
    output = root / "private-review-do-not-write.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/chart_review.py",
            "--source",
            str(public_chart_path),
            "--output",
            str(output),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "outside public repository" in result.stderr
    assert not output.exists()
