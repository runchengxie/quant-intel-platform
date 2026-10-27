"""Locales preserve warning and numeric contracts through public report import."""

from datetime import datetime

import pytest

from a_share_daily import public_report_refresh
from a_share_daily.freshness import build_freshness_report
from a_share_daily.morning_report import render_morning_report
from market_intel_commentary.insight_contract import build_context
from market_intel_publication.import_reports import parse_markdown


class PublicationClock(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 6, 30, 7, 5, tzinfo=tz)


def prior_close() -> dict:
    return parse_markdown(
        "# Prior close\n生成时间: 2026-06-29 18:00\n\n"
        "## Metrics\n上涨率55.0%\n成交额/历史中位1.2x\n站上VWAP比例60.0%\n",
        "2026-06-29",
        "evening",
    )


def warning_evidence(context: dict) -> list[tuple[str, str]]:
    return [
        (item["id"], "[WARN]" if item["text"].startswith("- [WARN]") else "[fetch]")
        for item in context["evidence"]
        if item["text"] in context["quality_warnings"]
    ]


@pytest.mark.parametrize(
    ("scenario", "expected_count"),
    [
        ("empty", 6),
        ("optional_degraded", 6),
        ("all_fresh", 5),
        ("stale_macro", 5),
    ],
)
def test_public_morning_context_keeps_quality_warnings_and_metrics_across_locales(
    monkeypatch,
    scenario: str,
    expected_count: int,
) -> None:
    monkeypatch.setattr(public_report_refresh, "datetime", PublicationClock)
    manifest = {"date": "20260630", "date_dash": "2026-06-30", "cross_market": {}}
    if scenario != "empty":
        latest = {"daily": "20260630"}
        if scenario == "optional_degraded":
            latest["moneyflow_ths"] = None
        manifest["freshness"] = build_freshness_report(
            latest_by_dataset=latest,
            target_date="20260630",
            premium_enabled=False,
        )
    if scenario == "stale_macro":
        manifest["cross_market"] = {
            "macros": {
                "^VIX": {
                    "label": "VIX 恐慌指数",
                    "close": 18.2,
                    "pct_chg": -1,
                    "as_of_date": "2026-06-24",
                    "stale_days": 6,
                }
            }
        }
    contexts = {}
    evening = prior_close()
    for locale in ("en-US", "zh-CN"):
        rendered = render_morning_report(
            manifest,
            {},
            generated_at=datetime(2026, 6, 30, 7),
            locale=locale,
        )
        public = public_report_refresh.public_markdown(
            rendered,
            "20260630",
            "morning",
            "scheduled",
        )
        morning = parse_markdown(public, "2026-06-30", "morning")
        context = build_context([morning, evening], morning, evening)
        assert len(context["quality_warnings"]) == expected_count
        assert not any("stale/missing 0" in text for text in context["quality_warnings"])
        if scenario == "optional_degraded":
            optional = [text for text in context["quality_warnings"] if "moneyflow_ths" in text]
            assert len(optional) == 1
            assert optional[0].startswith("- [fetch]")
        if scenario == "stale_macro":
            assert any("18.20 (-1.00%)" in text for text in context["quality_warnings"])
        assert {key: value["value"] for key, value in context["metrics"].items()} == {
            "advancing_pct": 55.0,
            "volume_ratio": 1.2,
            "above_vwap_pct": 60.0,
        }
        contexts[locale] = context
    english, chinese = contexts["en-US"], contexts["zh-CN"]
    for key in (
        "date",
        "as_of",
        "morning_report_id",
        "evening_report_id",
        "source_report_ids",
        "metrics",
    ):
        assert english[key] == chinese[key]
    assert warning_evidence(english) == warning_evidence(chinese)
    # Source hashes/evidence text bind the localized bytes, not translated business facts.


def test_context_preserves_legacy_unmarked_chinese_quality_notes() -> None:
    morning = parse_markdown(
        "# Morning\n生成时间: 2026-06-30 07:00\n\n## Quality\n原始数据暂缺。\n",
        "2026-06-30",
        "morning",
    )
    evening = prior_close()
    context = build_context([morning, evening], morning, evening)
    assert context["quality_warnings"] == ["原始数据暂缺。"]
