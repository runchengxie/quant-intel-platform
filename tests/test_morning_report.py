from datetime import datetime

from a_share_daily.morning_report import render_morning_report


def test_morning_report_uses_structured_facts_only() -> None:
    manifest = {
        "date": "20260630",
        "date_dash": "2026-06-30",
        "hotsector": {"ok": True, "candidates": 42},
        "cross_market": {
            "us_stocks": {
                "SPY": {"close": 520.0, "pct_chg": 0.4},
                "QQQ": {"close": 450.0, "pct_chg": 0.8},
                "SMH": {"close": 250.0, "pct_chg": -1.2},
                "NVDA": {"close": 130.0, "pct_chg": -2.1},
                "MSFT": {"close": 410.0, "pct_chg": 1.5},
                "^N225": {"close": 39500.0, "pct_chg": 0.6},
                "^KS11": {"close": 2800.0, "pct_chg": -0.3},
                "8035.T": {"close": 31000.0, "pct_chg": 2.4},
                "000660.KS": {"close": 210000.0, "pct_chg": 1.1},
            },
            "global_lead_lag": [
                {
                    "concept": "半导体设备",
                    "avg_pct_chg": 1.8,
                    "signal": "bullish",
                    "drivers": ["8035.T +2.4%", "000660.KS +1.1%"],
                    "markets": ["JP", "KR"],
                }
            ],
            "macros": {
                "^VIX": {
                    "label": "VIX 恐慌指数",
                    "close": 18.2,
                    "pct_chg": -1.0,
                    "as_of_date": "2026-06-29",
                },
                "DX-Y.NYB": {"label": "DXY 美元指数", "close": 101.2, "pct_chg": 0.1},
            },
            "aaii_sentiment": {
                "bullish_pct": 40.0,
                "bearish_pct": 30.0,
                "bull_bear_spread": 10.0,
            },
        },
    }
    news = {
        "markets": {
            "cn": {
                "items": [
                    {
                        "category": "policy",
                        "title": "政策发布",
                        "summary": "监管部门发布新的市场制度安排。",
                        "source": "证监会",
                        "url": "https://example.com/policy",
                        "published_at": "2026-06-30",
                    },
                    {
                        "category": "macro",
                        "title": "无链接消息",
                        "summary": "这条消息不应进入报告。",
                        "source": "某媒体",
                    },
                ]
            }
        }
    }

    text = render_morning_report(
        manifest,
        news,
        generated_at=datetime(2026, 6, 30, 7, 0),
    )

    assert "未使用自由写作流程" in text
    assert "监管部门发布新的市场制度安排" in text
    assert "无链接消息" not in text
    assert "SPY +0.40%" in text
    assert "半导体设备" in text
    assert "热点候选池 42 只" in text
    assert "VIX 恐慌指数" in text


def test_morning_report_marks_empty_hotsector_and_stale_macro() -> None:
    manifest = {
        "date": "20260630",
        "date_dash": "2026-06-30",
        "hotsector": {
            "ok": False,
            "candidates": 0,
            "reason": "hotsector 产出 0 只候选，概念数据暂缺",
        },
        "cross_market": {
            "_freshness_warnings": ["VIX 恐慌指数 快照日期为 2026-06-25，滞后 6 天"],
            "macros": {
                "^VIX": {
                    "label": "VIX 恐慌指数",
                    "close": 18.2,
                    "pct_chg": -1.0,
                    "as_of_date": "2026-06-25",
                    "stale_days": 6,
                },
                "^TNX": {
                    "label": "10Y 美债收益率",
                    "close": 4.4,
                    "pct_chg": -0.2,
                    "as_of_date": "2026-06-25",
                    "stale_days": 6,
                },
            },
        },
    }

    text = render_morning_report(
        manifest,
        {},
        generated_at=datetime(2026, 7, 1, 7, 0),
    )

    assert "热点候选池为空（hotsector 产出 0 只候选，概念数据暂缺）" in text
    assert "[WARN] VIX 恐慌指数 快照日期为 2026-06-25，滞后 6 天。" in text
    assert "[WARN] VIX 恐慌指数: 18.20 (-1.00%)，截至 2026-06-25，滞后 6 天" in text


def test_morning_report_omits_hotsector_warning_when_premium_skipped() -> None:
    manifest = {
        "date": "20260630",
        "date_dash": "2026-06-30",
        "hotsector": {
            "ok": False,
            "skipped": True,
            "candidates": 0,
            "reason": "高权限 TuShare 主题数据未启用",
        },
        "cross_market": {
            "global_lead_lag": [
                {
                    "concept": "AI芯片",
                    "avg_pct_chg": 2.4,
                    "signal": "bullish",
                    "drivers": ["NVDA +2.4%"],
                }
            ]
        },
    }

    text = render_morning_report(
        manifest,
        {},
        generated_at=datetime(2026, 7, 1, 7, 0),
    )

    assert "热点候选池为空" not in text
    assert "高权限 TuShare" not in text
    assert "关注映射: AI芯片" in text
