"""Offline public weekly boundary tests."""

import pytest

from market_intel_publication.weekly_recap_contract import validate_weekly_recap


def test_private_payload_rejected():
    with pytest.raises(ValueError):
        validate_weekly_recap({"publication": "private"})


def test_export_requires_explicit_public(tmp_path):
    from market_intel_publication.weekly_recap_bundle import WeeklyInputs, export_bundle

    with pytest.raises(ValueError, match="public"):
        export_bundle(
            WeeklyInputs(
                tmp_path / "report", tmp_path / "image", tmp_path / "value", tmp_path / "size"
            ),
            "2026-10-23",
            tmp_path / "out",
            "private",
        )


def test_invalid_timestamp_raises_valueerror():
    from market_intel_publication.weekly_recap_contract import content_hash

    payload = dict.fromkeys(
        [
            "schema_version",
            "publication",
            "report_id",
            "date",
            "generated_at",
            "content_hash",
            "markdown",
            "source_url",
            "image",
            "summary",
            "series",
            "sources",
        ]
    )
    payload.update(
        schema_version="market_intel_pages.weekly_recap.v1",
        publication="public",
        report_id="2026-10-23-weekly",
        date="2026-10-23",
    )
    payload["content_hash"] = content_hash(payload)
    with pytest.raises(ValueError):
        validate_weekly_recap(payload)
