from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from a_share_analysis import value_regime_weekly as vr
from a_share_analysis.value_weekly_chart import generate_value_weekly_card


def _weekly_frame(n: int = 120, seed: int = 3) -> pd.DataFrame:
    """Build a deterministic weekly-return frame with enough history."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2023-01-06", periods=n, freq="W-FRI")
    returns = pd.Series(rng.normal(0.001, 0.02, size=n), index=idx, name="weekly_return")
    return returns.to_frame()


def _visible_markdown(markdown: str) -> str:
    """Remove Markdown link destinations before checking visible punctuation."""
    return re.sub(r"\]\([^)]*\)", "]", markdown)


def test_owner_artifact_loader_reconstructs_report_inputs(tmp_path: Path) -> None:
    path = tmp_path / "value-artifact.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "research.weekly_analysis.v1",
                "artifact_type": "value_regime_weekly",
                "as_of": "20250502",
                "quality": {"status": "passed", "observation_count": 1},
                "snapshot": {"regime": "NEUTRAL"},
                "patterns": {"NEUTRAL": {}, "ALL": {}},
                "weekly_features": [
                    {
                        "date": "20250502",
                        "weekly_return": 0.01,
                        "ret_4w": 0.02,
                        "ret_12w": 0.03,
                        "ret_52w": 0.04,
                        "vol_12w": 0.1,
                        "drawdown": -1.0,
                        "max_drawdown_full": -2.0,
                        "up_ratio_12w": 0.5,
                        "regime": "NEUTRAL",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    df, patterns, snapshot = vr.load_owner_artifact(path, expected_through="20250502")

    assert df.iloc[-1]["regime"] == "NEUTRAL"
    assert patterns["ALL"] == {}
    assert snapshot["regime"] == "NEUTRAL"


def test_owner_artifact_string_as_of_is_safe_for_expected_cutoff_comparison(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[dict] = []

    monkeypatch.setattr(
        vr,
        "load_owner_artifact",
        lambda *_args, **_kwargs: (pd.DataFrame(), {}, {"as_of": "20260828"}),
    )
    monkeypatch.setattr(vr, "_resolve_comparison_series", lambda: [("base", "基础", tmp_path)])
    monkeypatch.setattr(
        vr,
        "generate_report",
        lambda *_args, comparisons=None, **_kwargs: seen.extend(comparisons or []) or "ok",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "value_regime_weekly.py",
            "--artifact",
            "artifact.json",
            "--expected-through",
            "20260828",
            "--out",
            str(tmp_path / "out.md"),
        ],
    )

    vr.main()

    assert seen == [{"label": "基础", "fresh": True, "as_of": "20260828"}]


def test_compute_features_uses_compounded_returns() -> None:
    source = _weekly_frame()
    df = vr.compute_features(source)

    for col in [
        "ret_4w",
        "ret_12w",
        "ret_52w",
        "vol_12w",
        "cum",
        "cum_max",
        "drawdown",
        "up_ratio_12w",
    ]:
        assert col in df.columns

    expected_12w = (1 + source["weekly_return"].iloc[-12:]).prod() - 1
    assert df["ret_12w"].iloc[-1] == expected_12w
    assert df["cum_max"].is_monotonic_increasing
    assert (df["drawdown"] <= 1e-9).all()


def test_assign_regime_uses_two_supported_states() -> None:
    df = vr.compute_features(_weekly_frame(n=60))
    labeled = vr.assign_regime(df)

    assert set(labeled["regime"].unique()).issubset({"MOMENTUM", "NEUTRAL"})

    strong = df.iloc[-1:].copy()
    strong["ret_12w"] = 0.10
    assert vr.assign_regime(strong).iloc[0]["regime"] == "MOMENTUM"

    weak = df.iloc[-1:].copy()
    weak["ret_12w"] = -0.30
    assert vr.assign_regime(weak).iloc[0]["regime"] == "NEUTRAL"


def test_forward_compound_uses_the_next_h_weeks_without_offset_leakage() -> None:
    weekly = pd.Series([0.10, 0.20, 0.30, 0.40], index=pd.RangeIndex(4))

    forward = vr._forward_compound(weekly, 2)

    assert forward.iloc[0] == pytest.approx((1.20 * 1.30) - 1)
    assert forward.iloc[1] == pytest.approx((1.30 * 1.40) - 1)
    assert forward.iloc[2:].isna().all()


def test_expected_cutoff_prevents_backfill_reports_from_using_future_data() -> None:
    daily = pd.Series(
        [0.01, 0.02, 0.03],
        index=pd.to_datetime(["2026-07-30", "2026-07-31", "2026-08-03"]),
    )

    truncated = vr._truncate_at_expected(daily, date(2026, 7, 31))

    assert truncated.index.max() == pd.Timestamp("2026-07-31")
    assert len(truncated) == 2


def test_historical_patterns_reports_observations_and_episodes() -> None:
    df = vr.assign_regime(vr.compute_features(_weekly_frame(n=160)))
    patterns = vr.historical_patterns(df)

    assert set(patterns) == {"MOMENTUM", "NEUTRAL", "ALL"}
    assert patterns["ALL"]["count"] == len(df)
    assert patterns["ALL"]["episode_count"] == 1
    assert patterns["MOMENTUM"]["episode_count"] <= patterns["MOMENTUM"]["count"]
    for regime in patterns:
        summary = patterns[regime]["fwd_returns"]["13w"]
        assert {"sample_count", "mean", "median", "q25", "q75", "win_rate"} <= set(summary)


def test_load_weekly_returns_resamples_to_friday_weekly(tmp_path: Path) -> None:
    csv = "date,ls_return\n" + "\n".join(
        f"2024-01-0{day},0.01" if day <= 9 else f"2024-01-{day},0.01" for day in range(1, 15)
    )
    path = tmp_path / "factor_value_daily.csv"
    path.write_text(csv, encoding="utf-8")
    original = vr.FACTOR_CSV
    vr.FACTOR_CSV = path
    try:
        daily = vr.load_daily_returns()
        out = vr.load_weekly_returns(daily)
    finally:
        vr.FACTOR_CSV = original

    assert (out.index.dayofweek == 4).all()
    assert (out["weekly_return"] > 0).all()
    assert daily.index.max() == pd.Timestamp("2024-01-14")


def test_generate_report_marks_incomplete_data_and_avoids_markdown_tables() -> None:
    df = vr.assign_regime(vr.compute_features(_weekly_frame(n=160)))
    patterns = vr.historical_patterns(df)
    status = vr.FactorDataStatus(
        source_path=Path("factor_value_daily.csv"),
        as_of=date(2026, 7, 29),
        expected_through=date(2026, 7, 31),
    )
    market = "## 本周复盘（07/27–07/31）\n\n外盘黄金：[OK] 本周走高。"

    report = vr.generate_report(df, patterns, data_status=status, market_context=market)

    assert "数据状态：尚未完整" in report
    assert "当前数据截至 2026-07-29" in report
    assert "目标日期为 2026-07-31" in report
    assert report.startswith("# 本周市场背景")
    assert report.index("# 本周市场背景") < report.index("# 市场风格周报")
    assert report.index("# 市场风格周报") < report.index("## 价值因子")
    assert "## 价值因子" in report
    assert "<!--" not in report
    assert "[OK]" not in report
    assert "外盘黄金：本周走高" in report
    assert "|------" not in report
    assert "深度折价" not in report
    assert "计算方法、图表说明和数据范围" in report
    visible = _visible_markdown(report)
    assert "**" not in visible
    assert not any(mark in visible for mark in ("“", "”", "；", "——", "(", ")"))
    assert not re.search(r"不是.*而是", visible)


def test_series_snapshot_computes_key_metrics_from_daily_returns() -> None:
    rng = np.random.default_rng(7)
    idx = pd.date_range("2023-01-02", periods=600, freq="B")
    daily = pd.Series(rng.normal(0.0005, 0.01, size=len(idx)), index=idx)

    snap = vr.series_snapshot(daily)

    assert snap["as_of"] == idx[-1].date()
    assert snap["regime"] in {"MOMENTUM", "NEUTRAL"}
    assert {"ret12w", "ret52w", "drawdown", "fwd13_median", "fwd13_winrate"} <= set(snap)
    assert snap["streak"] >= 1
    assert snap["count"] >= 1


def test_value_card_uses_signal_as_hero_and_editorial_sections(tmp_path: Path) -> None:
    df = vr.assign_regime(vr.compute_features(_weekly_frame(n=180)))
    patterns = vr.historical_patterns(df)
    output = tmp_path / "value-weekly.png"

    generate_value_weekly_card(
        df,
        patterns,
        as_of_date=df.index[-1].date(),
        expected_through=None,
        out_path=output,
    )

    assert output.is_file()


def test_generate_report_includes_comparison_section() -> None:
    df = vr.assign_regime(vr.compute_features(_weekly_frame(n=160)))
    patterns = vr.historical_patterns(df)
    comparisons = [
        {
            "label": "基础市净率倒数",
            "fresh": True,
            "as_of": "20260807",
            "ret12w": 6.6,
            "percentile": 85.0,
            "ret52w": -0.2,
            "drawdown": -6.5,
            "fwd13_median": 1.6,
            "fwd13_winrate": 67.0,
        },
        {
            "label": "可交易筛选，已扣费用",
            "fresh": False,
            "as_of": date(2026, 7, 31),
            "ret12w": 5.0,
            "percentile": 70.0,
            "ret52w": 1.0,
            "drawdown": -3.0,
            "fwd13_median": 1.4,
            "fwd13_winrate": 64.0,
        },
    ]

    report = vr.generate_report(df, patterns, comparisons=comparisons)

    assert "### 不同计算方法" in report
    assert "基础市净率倒数" in report
    assert "历史回算" in report
    assert "后续 13 周收益中位数 +1.6%，正收益比例 67%" in report
    # 静态解释已移入文档，消息只保留当期数字
    assert "只看市净率一个便宜信号" not in report
    assert "## 图表解读" not in report
    assert "## 方法与边界" not in report
    assert "各方法的含义见说明文档" in report
    assert "|------" not in report
    # 飞书说明文档链接
    assert "周报怎么读" in report
    assert "https://example.com/weekly-methodology" in report
    visible = _visible_markdown(report)
    assert "**" not in visible
    assert not any(mark in visible for mark in ("“", "”", "；", "——", "(", ")"))
    assert not re.search(r"不是.*而是", visible)


def test_generate_value_weekly_card_is_portrait(tmp_path: Path) -> None:
    df = vr.assign_regime(vr.compute_features(_weekly_frame(n=180)))
    patterns = vr.historical_patterns(df)
    out = tmp_path / "value_weekly_card.png"

    result = generate_value_weekly_card(
        df,
        patterns,
        as_of_date=date(2026, 7, 29),
        expected_through=date(2026, 7, 31),
        out_path=out,
    )

    image = plt.imread(result)
    assert out.is_file()
    assert image.shape[0] > image.shape[1]
    assert image.shape[0] >= 1400
    assert image.shape[1] >= 1100
