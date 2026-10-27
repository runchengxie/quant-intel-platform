"""Presentation locales must preserve source content and immutable report inputs."""

import re
from copy import deepcopy
from datetime import datetime

import pytest

from a_share_daily.delivery.report_delivery import build_evening_summary
from a_share_daily.freshness import build_freshness_report
from a_share_daily.morning_report import render_morning_report


def test_english_empty_report_templates_are_fully_localized() -> None:
    morning = render_morning_report({}, {}, generated_at=datetime(2026, 6, 30, 7))
    evening = build_evening_summary(
        "20260630",
        review_payload={},
        news_payload={},
        manifest_payload={},
        generated_at=datetime(2026, 6, 30, 18),
    )
    assert not re.search(r"[\u4e00-\u9fff]", morning)
    assert not re.search(r"[\u4e00-\u9fff]", evening)
    assert "Missing SPY/QQQ/SMH benchmark quotes" in morning
    assert "Market temperature data is insufficient" in evening


@pytest.mark.parametrize("locale", ["en-US", "zh-CN"])
def test_locale_preserves_source_statements_and_all_structured_facts(locale: str) -> None:
    source = "原文含 ## 1. 隔夜要闻，不应改写"
    news = {
        "markets": {
            "cn": {
                "items": [
                    {
                        "category": "policy",
                        "summary": source,
                        "title": source,
                        "source": "来源机构",
                        "url": "https://example.test/evidence-17",
                        "published_at": "2026-06-30",
                    }
                ]
            }
        }
    }
    manifest = {
        "date": "20260630",
        "date_dash": "2026-06-30",
        "cross_market": {"us_stocks": {"SPY": {"close": 520.0, "pct_chg": 0.4}}},
        "freshness": build_freshness_report(
            latest_by_dataset={"daily": "20260630", "margin": "20260629"},
            target_date="20260630",
            premium_enabled=False,
        ),
    }
    review = {
        "overview": {
            "median_pct_chg": 0.25,
            "wavg_pct_chg": -0.5,
            "turnover_total": 100000,
            "breadth": {"up": 12, "down": 8, "up_ratio": 60},
        },
        "hot_sectors": {"top_by_change": [{"name": "原始概念", "pct_change": 2.5}]},
    }
    before = deepcopy((news, manifest, review))
    morning = render_morning_report(manifest, news, locale=locale)
    evening = build_evening_summary(
        "20260630",
        review_payload=review,
        news_payload=news,
        manifest_payload=manifest,
        locale=locale,
    )
    assert (news, manifest, review) == before
    for text in (morning, evening):
        assert source in text
        assert "来源机构" in text
        assert "https://example.test/evidence-17" in text
        assert "2026-06-30" in text
    assert "SPY +0.40%" in morning
    assert "+0.25%" in evening and "-0.50%" in evening
    assert "原始概念(+2.50%)" in evening


def test_english_freshness_localizes_known_contract_metadata_only() -> None:
    freshness = build_freshness_report(
        latest_by_dataset={"daily": None, "margin": "20260629"},
        target_date="20260630",
        premium_enabled=False,
    )
    output = render_morning_report({"freshness": freshness}, {})
    assert "Target trading date 2026-06-30" in output
    assert "A-share daily prices(daily)" in output
    assert not re.search(r"[\u4e00-\u9fff]", output)


def test_catalog_falls_back_to_english_and_rejects_unknown_locales(monkeypatch) -> None:
    from a_share_daily import report_messages

    monkeypatch.setitem(report_messages.MESSAGES, "fixture.fallback", {"en-US": "Value {value}"})
    assert report_messages.message("zh-CN", "fixture.fallback", value="17") == "Value 17"
    with pytest.raises(ValueError, match="Unsupported locale"):
        report_messages.message("fr-FR", "fixture.fallback", value="17")


def test_catalog_locales_have_the_same_interpolation_contract() -> None:
    from string import Formatter

    from a_share_daily.report_messages import MESSAGES

    for translations in MESSAGES.values():
        english_fields = {
            field for _, field, _, _ in Formatter().parse(translations["en-US"]) if field
        }
        for template in translations.values():
            assert {
                field for _, field, _, _ in Formatter().parse(template) if field
            } == english_fields


@pytest.mark.parametrize(
    "value, prefix", [(1e12, "1.00"), (1e8, "1.00"), (1e4, "1.00"), (-20, "-20")]
)
def test_currency_locale_preserves_magnitude_and_sign(value: float, prefix: str) -> None:
    from a_share_daily.delivery._format import _fmt_yuan

    assert _fmt_yuan(value, locale="zh-CN").startswith(prefix)
    assert _fmt_yuan(value, locale="en-US").startswith(prefix)
    assert "CNY" in _fmt_yuan(value, locale="en-US")
    assert not re.search(r"[\u4e00-\u9fff]", _fmt_yuan(value, locale="en-US"))
