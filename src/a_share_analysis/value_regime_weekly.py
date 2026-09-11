"""Generate the industry-neutral Value factor weekly report and decision card."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd

from a_share_analysis.value_weekly_chart import generate_value_weekly_card
from a_share_analysis.weekly_analysis_artifact import load_weekly_analysis_artifact
from market_intel_config import data_platform_root

PROJECT_ROOT = Path(__file__).resolve().parents[2]

STYLE_OUTPUTS_DIR = Path(".market-intel-external-data-not-configured/style-factors")
OUT_DIR = PROJECT_ROOT / "artifacts" / "value_regime"

MOMENTUM_12W_THRESHOLD = 0.05
REGIMES = ("MOMENTUM", "NEUTRAL")
FORWARD_HORIZONS = ((4, "4w"), (13, "13w"), (26, "26w"), (52, "52w"))

# 周报阅读说明飞书文档，用大白话解释口径与图表读法。
DEFAULT_WEEKLY_DOC_URL = "https://example.com/weekly-methodology"


def _resolve_weekly_doc_url() -> str | None:
    return os.environ.get("A_SHARE_WEEKLY_DOC_URL", DEFAULT_WEEKLY_DOC_URL) or None


def _resolve_factor_csv() -> Path:
    """Resolve the neutralized Value CSV from the published latest version."""
    override = os.environ.get("A_SHARE_VALUE_FACTOR_CSV")
    if override:
        return Path(override)
    style_outputs_dir = STYLE_OUTPUTS_DIR
    if style_outputs_dir == Path(".market-intel-external-data-not-configured/style-factors"):
        style_outputs_dir = data_platform_root(required=True) / "strategy_outputs" / "style-factors"
    latest_ptr = style_outputs_dir / "latest.txt"
    version = latest_ptr.read_text(encoding="utf-8").strip() if latest_ptr.exists() else "latest"
    return style_outputs_dir / version / "factor_value_daily.csv"


FACTOR_CSV = _resolve_factor_csv()


@dataclass(frozen=True)
class FactorDataStatus:
    """Actual factor coverage versus the report's requested cutoff."""

    source_path: Path
    as_of: date
    expected_through: date | None = None

    @property
    def is_complete(self) -> bool:
        return self.expected_through is None or self.as_of >= self.expected_through

    @property
    def freshness_label(self) -> str:
        if self.is_complete:
            return "数据完整"
        return f"数据未覆盖目标日 {self.expected_through:%Y-%m-%d}"


def load_daily_returns(path: Path | str | None = None) -> pd.Series:
    """Load a published daily long-short return series with schema checks."""
    source = Path(path) if path else FACTOR_CSV
    raw = pd.read_csv(source)
    if raw.shape[1] < 2:
        raise ValueError(f"Value 因子文件至少需要日期列和收益列：{source}")
    dates = pd.to_datetime(raw.iloc[:, 0], errors="coerce")
    values = pd.to_numeric(raw.iloc[:, 1], errors="coerce")
    daily = pd.Series(values.to_numpy(), index=pd.DatetimeIndex(dates), name="ls_return")
    daily = daily.dropna().sort_index()
    if daily.empty:
        raise ValueError(f"Value 因子文件没有可用收益：{source}")
    if daily.index.has_duplicates:
        raise ValueError(f"Value 因子文件包含重复日期：{source}")
    return daily


def load_weekly_returns(daily_returns: pd.Series | None = None) -> pd.DataFrame:
    """Compound daily returns into Friday-anchored weekly returns."""
    daily = load_daily_returns() if daily_returns is None else daily_returns
    weekly = daily.resample("W-FRI").apply(lambda values: (1 + values).prod() - 1).dropna()
    return weekly.rename("weekly_return").to_frame()


def _rolling_compound(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window).apply(lambda values: np.prod(1 + values) - 1, raw=True)


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute compounded weekly regime features."""
    df = df.copy()
    df["ret_4w"] = _rolling_compound(df["weekly_return"], 4)
    df["ret_12w"] = _rolling_compound(df["weekly_return"], 12)
    df["ret_52w"] = _rolling_compound(df["weekly_return"], 52)
    df["vol_12w"] = df["weekly_return"].rolling(12).std() * np.sqrt(52)
    df["cum"] = (1 + df["weekly_return"]).cumprod()
    df["cum_max"] = df["cum"].cummax()
    df["drawdown"] = (df["cum"] / df["cum_max"] - 1) * 100
    df["max_drawdown_full"] = float(df["drawdown"].min())
    df["up_ratio_12w"] = df["weekly_return"].rolling(12).apply(lambda values: (values > 0).mean())
    return df.dropna(subset=["ret_52w", "vol_12w", "up_ratio_12w"])


def assign_regime(df: pd.DataFrame) -> pd.DataFrame:
    """Assign the two empirically supported regimes."""
    df = df.copy()
    df["regime"] = np.where(
        df["ret_12w"] > MOMENTUM_12W_THRESHOLD,
        "MOMENTUM",
        "NEUTRAL",
    )
    return df


def _forward_compound(series: pd.Series, horizon: int) -> pd.Series:
    gross = 1 + series
    return gross.rolling(horizon).apply(np.prod, raw=True).shift(-horizon) - 1


def _return_summary(values: pd.Series) -> dict[str, float | int]:
    values = values.dropna()
    return {
        "sample_count": len(values),
        "mean": round(values.mean() * 100, 1),
        "median": round(values.median() * 100, 1),
        "q25": round(values.quantile(0.25) * 100, 1),
        "q75": round(values.quantile(0.75) * 100, 1),
        "win_rate": round((values > 0).mean() * 100, 0),
    }


def _episode_entry_mask(mask: pd.Series) -> pd.Series:
    return mask & ~mask.shift(fill_value=False)


def historical_patterns(df: pd.DataFrame) -> dict[str, dict]:
    """Summarize overlapping weekly observations and episode-entry robustness."""
    forward = {
        label: _forward_compound(df["weekly_return"], horizon)
        for horizon, label in FORWARD_HORIZONS
    }
    patterns: dict[str, dict] = {}
    for regime in (*REGIMES, "ALL"):
        mask = pd.Series(True, index=df.index) if regime == "ALL" else df["regime"].eq(regime)
        entries = _episode_entry_mask(mask)
        patterns[regime] = {
            "count": int(mask.sum()),
            "pct_of_total": round(mask.mean() * 100, 1),
            "episode_count": int(entries.sum()),
            "fwd_returns": {
                label: _return_summary(values.loc[mask]) for label, values in forward.items()
            },
            "entry_fwd_returns": {
                label: _return_summary(values.loc[entries]) for label, values in forward.items()
            },
        }
    return patterns


def current_streak(df: pd.DataFrame) -> int:
    """Return consecutive weeks spent in the current regime."""
    regime = df["regime"].iloc[-1]
    return int(df["regime"].iloc[::-1].eq(regime).cumprod().sum())


def _regime_label(regime: str) -> str:
    return "趋势延续" if regime == "MOMENTUM" else "中性"


def analyze_series(daily_returns: pd.Series) -> tuple[pd.DataFrame, dict, dict]:
    """Compute weekly features, regime patterns and the report snapshot for a series."""
    weekly = load_weekly_returns(daily_returns)
    df = assign_regime(compute_features(weekly))
    if df.empty:
        raise ValueError("序列不足，无法计算周频特征")
    last = df.iloc[-1]
    regime = str(last["regime"])
    patterns = historical_patterns(df)
    fwd13 = patterns[regime]["fwd_returns"]["13w"]
    percentile = float((df["ret_12w"] <= last["ret_12w"]).mean() * 100)
    snapshot = {
        "as_of": df.index[-1].date(),
        "regime": regime,
        "regime_name": _regime_label(regime),
        "streak": current_streak(df),
        "ret12w": last["ret_12w"] * 100,
        "percentile": percentile,
        "ret52w": last["ret_52w"] * 100,
        "drawdown": last["drawdown"],
        "vol12w": last["vol_12w"] * 100,
        "up12w": last["up_ratio_12w"] * 100,
        "fwd13_median": fwd13["median"],
        "fwd13_winrate": fwd13["win_rate"],
        "count": int(patterns[regime]["count"]),
    }
    return df, patterns, snapshot


def series_snapshot(daily_returns: pd.Series) -> dict:
    """Recompute the report's key metrics for an arbitrary value-family series."""
    _, _, snapshot = analyze_series(daily_returns)
    return snapshot


def load_owner_artifact(
    path: Path | str, *, expected_through: str | None = None
) -> tuple[pd.DataFrame, dict, dict]:
    """Reconstruct report inputs from the research-owned Value artifact."""
    payload = load_weekly_analysis_artifact(
        Path(path), artifact_type="value_regime_weekly", expected_as_of=expected_through
    )
    rows = payload["weekly_features"]
    frame = pd.DataFrame(rows)
    frame["date"] = pd.to_datetime(frame.pop("date"))
    frame = frame.set_index("date").sort_index()
    numeric = [column for column in frame.columns if column != "regime"]
    frame[numeric] = frame[numeric].apply(pd.to_numeric, errors="raise")
    return frame, payload["patterns"], payload["snapshot"]


def _resolve_comparison_series() -> list[tuple[str, str, Path]]:
    """Resolve the value-family series for the 口径对照 section.

    Returns ``(key, label, path)`` tuples. The base 1/PB series always exists;
    the value-cluster composite is optional (present after the research pipeline
    publishes it); the constrained gross/net series are optional 封存 reference
    outputs from the latest ``*constrained*`` robustness run.
    """
    series: list[tuple[str, str, Path]] = [("base", "基础市净率倒数", FACTOR_CSV)]
    cluster = FACTOR_CSV.parent / "factor_value_cluster_daily.csv"
    if cluster.is_file():
        series.append(("cluster", "综合价值指标", cluster))
    constrained_dir_raw = os.environ.get("A_SHARE_VALUE_CONSTRAINED_DIR")
    constrained_dir = Path(constrained_dir_raw) if constrained_dir_raw else None
    if constrained_dir is None or not constrained_dir.is_dir():
        candidates = sorted(STYLE_OUTPUTS_DIR.glob("*constrained*"), reverse=True)
        for candidate in candidates:
            if (
                candidate.is_dir()
                and (candidate / "factor_value_constrained_gross_daily.csv").is_file()
            ):
                constrained_dir = candidate
                break
    if constrained_dir is not None and constrained_dir.is_dir():
        gross = constrained_dir / "factor_value_constrained_gross_daily.csv"
        net = constrained_dir / "factor_value_constrained_net_daily.csv"
        if gross.is_file():
            series.append(("cons_gross", "可交易筛选，未扣费用", gross))
        if net.is_file():
            series.append(("cons_net", "可交易筛选，已扣费用", net))
    return series


def _format_return_line(horizon: str, summary: dict) -> str:
    display_horizon = horizon.removesuffix("w")
    return (
        f"- 后续 {display_horizon} 周：收益中位数 {summary['median']:+.1f}%，"
        f"正收益比例 {summary['win_rate']:.0f}%（{summary['sample_count']} 周样本）"
    )


def _normalize_market_context(markdown: str) -> list[str]:
    lines = []
    for line in markdown.strip().splitlines():
        if line.startswith("## 本周复盘"):
            continue
        lines.append(line.replace("[OK] ", "").replace("[WARN] ", ""))
    while lines and not lines[0].strip():
        lines.pop(0)
    return lines


def _render_comparison_section(comparisons: list[dict]) -> list[str]:
    lines = ["", "### 不同计算方法", ""]
    lines.append("各方法的含义见说明文档。本期数据如下：")
    lines.append("")
    for comp in comparisons:
        freshness = "" if comp.get("fresh") else "，历史回算"
        as_of = _snapshot_date(comp["as_of"])
        lines.append(
            f"- {comp['label']}（截至 {as_of:%Y-%m-%d}{freshness}）："
            f"过去 12 周累计 {comp['ret12w']:+.1f}%，高于约 {comp['percentile']:.0f}% 的历史样本。"
            f"过去 52 周累计 {comp['ret52w']:+.1f}%，当前回撤 {comp['drawdown']:.1f}%。"
            f"历史上，后续 13 周收益中位数 {comp['fwd13_median']:+.1f}%，"
            f"正收益比例 {comp['fwd13_winrate']:.0f}%。"
        )
    lines.append("")
    lines.append(
        "基础市净率倒数和综合价值指标每周更新。可交易筛选的两项结果来自最近一次单独回算，"
        "更新频率较低，截止日期也可能更早。比较时请先对齐数据日期。"
    )
    return lines


def _render_report_header(status: FactorDataStatus) -> list[str]:
    monday = status.as_of - timedelta(days=status.as_of.weekday())
    lines = [
        "# 市场风格周报",
        f"{monday:%Y-%m-%d} 当周，数据截至 {status.as_of:%Y-%m-%d}",
    ]
    doc_url = _resolve_weekly_doc_url()
    if doc_url:
        lines.extend(["", f"计算方法、图表说明和数据范围见[周报怎么读]({doc_url})。"])
    return lines


def _render_market_context(status: FactorDataStatus, markdown: str) -> list[str]:
    monday = status.as_of - timedelta(days=status.as_of.weekday())
    return [
        "# 本周市场背景",
        f"{monday:%Y-%m-%d} 当周，数据截至 {status.as_of:%Y-%m-%d}",
        "",
        *_normalize_market_context(markdown),
        "",
    ]


def generate_report(
    df: pd.DataFrame,
    patterns: dict[str, dict],
    *,
    data_status: FactorDataStatus | None = None,
    market_context: str | None = None,
    comparisons: list[dict] | None = None,
) -> str:
    """Generate a compact Feishu-friendly Markdown report."""
    last = df.iloc[-1]
    status = data_status or FactorDataStatus(FACTOR_CSV, df.index[-1].date())
    regime = str(last["regime"])
    regime_name = _regime_label(regime)
    streak = current_streak(df)
    percentile_12w = float((df["ret_12w"] <= last["ret_12w"]).mean() * 100)
    current_pattern = patterns[regime]
    baseline_pattern = patterns["ALL"]

    lines = _render_market_context(status, market_context) if market_context else []
    lines.extend(_render_report_header(status))
    lines.extend(["", "## 价值因子", "", "计算方法：行业中性化。", ""])
    if status.is_complete:
        lines.append("数据状态：完整，已覆盖本期目标截止日。")
    else:
        lines.append(
            f"数据状态：尚未完整。当前数据截至 {status.as_of:%Y-%m-%d}，"
            f"目标日期为 {status.expected_through:%Y-%m-%d}。本报告仅供预览。"
        )

    lines.extend(
        [
            "",
            "### 01 当前状态",
            "",
            f"{regime_name}，已持续 {streak} 周。",
            "",
            "### 02 证据",
            "",
            f"- 过去 12 周累计：{last['ret_12w'] * 100:+.1f}%（高于约 {percentile_12w:.0f}% 的历史样本）",
            f"- 过去 52 周累计：{last['ret_52w'] * 100:+.1f}%",
            f"- 当前回撤：{last['drawdown']:.1f}%（周频历史最大回撤 {last['max_drawdown_full']:.1f}%）",
            f"- 过去 12 周年化波动率：{last['vol_12w'] * 100:.1f}%",
            f"- 过去 12 周上涨周占比：{last['up_ratio_12w'] * 100:.0f}%",
            "",
            "### 03 历史参考",
            "",
            f"历史上，当前状态共出现 {current_pattern['count']} 周，"
            f"分布在 {current_pattern['episode_count']} 段连续时期。后续收益的统计区间有重叠，"
            "独立样本数少于周数。",
            "",
        ]
    )
    for _horizon, label in FORWARD_HORIZONS:
        lines.append(_format_return_line(label, current_pattern["fwd_returns"][label]))

    entry_13w = current_pattern["entry_fwd_returns"]["13w"]
    baseline_13w = baseline_pattern["fwd_returns"]["13w"]
    lines.extend(
        [
            "",
            f"只取每段状态的第一周，后续 13 周正收益比例为 {entry_13w['win_rate']:.0f}%"
            f"（{entry_13w['sample_count']} 个样本）。全样本的后续 13 周正收益比例为 "
            f"{baseline_13w['win_rate']:.0f}%。",
            "",
            "### 04 下周观察",
            "",
        ]
    )
    four_week = current_pattern["fwd_returns"]["4w"]
    thirteen_week = current_pattern["fwd_returns"]["13w"]
    if regime == "MOMENTUM":
        lines.extend(
            [
                f"- 历史上，后续 4 周正收益比例为 {four_week['win_rate']:.0f}%，短期方向不明显。",
                f"- 后续 13 周收益中位数为 {thirteen_week['median']:+.1f}%，"
                f"正收益比例为 {thirteen_week['win_rate']:.0f}%。历史上的中期收益多数为正。",
                "- 配置上可保持当前的价值风格比例，同时留意近期表现处于历史高位后的回落风险。",
            ]
        )
    else:
        lines.extend(
            [
                "- 当前方向不明显。",
                "- 配置上可保持当前的价值风格比例，避免根据单周波动频繁调整。",
            ]
        )

    if comparisons:
        lines.extend(_render_comparison_section(comparisons))

    return "\n".join(lines)


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        parsed = pd.Timestamp(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"无效日期：{raw}") from exc
    if pd.isna(parsed):
        raise argparse.ArgumentTypeError(f"无效日期：{raw}")
    return cast(date, parsed.date())


def _snapshot_date(value: object) -> date:
    """Normalize the JSON artifact's date representation for comparisons."""
    if isinstance(value, date):
        return value
    try:
        parsed = pd.Timestamp(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"无效的 artifact as_of：{value!r}") from exc
    if pd.isna(parsed):
        raise ValueError(f"无效的 artifact as_of：{value!r}")
    return cast(date, parsed.date())


def _truncate_at_expected(daily: pd.Series, expected_through: date | None) -> pd.Series:
    if expected_through is None:
        return daily
    truncated = daily.loc[: pd.Timestamp(expected_through)]
    if truncated.empty:
        raise ValueError(f"目标截止日之前没有 Value 因子数据：{expected_through}")
    return truncated


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Value factor weekly regime report")
    parser.add_argument("--out", help="Markdown output path (default: stdout)")
    parser.add_argument("--chart-out", help="Decision-card PNG output path")
    parser.add_argument("--market-context", help="Optional weekly market recap Markdown path")
    parser.add_argument("--expected-through", help="Required factor cutoff date, YYYYMMDD")
    parser.add_argument(
        "--artifact",
        help="Research-owned Value regime artifact; when set, no research calculation runs here",
    )
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Generate an explicitly marked preview when factor data misses the target cutoff",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    expected_through = _parse_date(args.expected_through)

    if args.artifact:
        print(f"[value_regime] Loading research artifact {args.artifact} ...", file=sys.stderr)
        df, patterns, base_snapshot = load_owner_artifact(
            args.artifact, expected_through=args.expected_through
        )
        status = FactorDataStatus(
            source_path=Path(args.artifact),
            as_of=cast(date, pd.Timestamp(base_snapshot["as_of"]).to_pydatetime().date()),
            expected_through=expected_through,
        )
    else:
        print(f"[value_regime] Loading {FACTOR_CSV} ...", file=sys.stderr)
        daily = _truncate_at_expected(load_daily_returns(), expected_through)
        status = FactorDataStatus(
            source_path=FACTOR_CSV,
            as_of=daily.index.max().date(),
            expected_through=expected_through,
        )
        if not status.is_complete and not args.allow_incomplete:
            print(
                f"[value_regime] 数据未覆盖目标截止日：actual={status.as_of}, "
                f"expected={status.expected_through}；拒绝生成生产周报",
                file=sys.stderr,
            )
            raise SystemExit(3)
        df, patterns, base_snapshot = analyze_series(daily)
    market_context = None
    if args.market_context and Path(args.market_context).is_file():
        market_context = Path(args.market_context).read_text(encoding="utf-8")

    comparisons: list[dict] = []
    cluster_chart: dict | None = None
    for key, label, path in _resolve_comparison_series():
        try:
            if key == "base":
                snap = base_snapshot
            else:
                _, _, snap = analyze_series(load_daily_returns(path))
        except Exception as exc:  # noqa: BLE001
            print(f"[value_regime] 跳过口径 {label}：{exc}", file=sys.stderr)
            continue
        fresh = expected_through is None or _snapshot_date(snap["as_of"]) >= expected_through
        comparisons.append({"label": label, "fresh": fresh, **snap})
        if key == "cluster":
            cluster_df, cluster_patterns, _ = analyze_series(load_daily_returns(path))
            cluster_chart = {"df": cluster_df, "patterns": cluster_patterns}

    report = generate_report(
        df,
        patterns,
        data_status=status,
        market_context=market_context,
        comparisons=comparisons,
    )

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
        print(f"[value_regime] Report written to {out_path}", file=sys.stderr)
    else:
        print(report)

    if args.chart_out:
        chart_path = generate_value_weekly_card(
            df,
            patterns,
            as_of_date=status.as_of,
            expected_through=status.expected_through,
            cluster=cluster_chart,
            out_path=args.chart_out,
        )
        print(f"[value_regime] Decision card written to {chart_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
