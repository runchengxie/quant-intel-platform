"""Generate the size-style weekly snapshot for the market weekly report.

Ported from wu-size-style-monitor: tracks crowding and relative strength
between the large-cap (CSI 300) and a small-cap proxy, and outputs the current
crowding regime plus the daily timing signal. Reads data-platform parquet.

Output is a compact Feishu-friendly Markdown snapshot intended to be appended
to the weekly value report, plus an optional crowding chart.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd

from a_share_analysis.weekly_analysis_artifact import load_weekly_analysis_artifact
from market_intel_config import data_platform_root

logger = logging.getLogger(__name__)

INDEX_DIR = Path(".market-intel-external-data-not-configured/index_daily")

DEFAULT_LARGE_INDEX = "000300.SH"
DEFAULT_SMALL_INDEX = "000852.SH"

MOMENTUM_WINDOWS = [10, 20, 30, 40, 50, 60]
CROWDING_THRESHOLDS = {"small_high": 0.9, "large_high": 0.1}
CROWDING_LOOKBACK_DAYS = 20


def _parse_timestamp(value: object, label: str) -> pd.Timestamp:
    try:
        parsed = pd.Timestamp(str(value))
    except ValueError as exc:
        raise ValueError(f"invalid {label}: {value}") from exc
    if pd.isna(parsed):
        raise ValueError(f"invalid {label}: {value}")
    return cast(pd.Timestamp, parsed)


def load_index_data(code: str) -> pd.DataFrame:
    """Load index daily bars for a code from the data-platform index_daily assets."""
    index_dir = INDEX_DIR
    if index_dir == Path(".market-intel-external-data-not-configured/index_daily"):
        index_dir = (
            data_platform_root(required=True) / "assets" / "tushare" / "a_share" / "index_daily"
        )
    frames: list[pd.DataFrame] = []
    for parquet_file in sorted(index_dir.rglob("*.parquet")):
        try:
            frame = pd.read_parquet(parquet_file)
        except Exception as exc:  # noqa: BLE001
            logger.debug("skip unreadable parquet %s: %s", parquet_file, exc)
            continue
        if "ts_code" not in frame.columns or "trade_date" not in frame.columns:
            continue
        frame = frame[frame["ts_code"] == code]
        if frame.empty:
            continue
        frame["trade_date"] = pd.to_datetime(frame["trade_date"])
        frames.append(frame)
    if not frames:
        raise FileNotFoundError(f"no index_daily data for {code} under {index_dir}")
    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates(subset=["trade_date"]).sort_values("trade_date")
    df = df.set_index("trade_date")
    if "amount" not in df.columns and "vol" in df.columns:
        df["amount"] = df["vol"].astype(float)
    return df


def _top3_average(values: np.ndarray) -> float:
    valid = values[~np.isnan(values)]
    if len(valid) >= 3:
        return float(np.mean(np.sort(valid)[-3:]))
    if len(valid) > 0:
        return float(np.mean(valid))
    return 0.5


def _crowding_series(
    large: pd.DataFrame,
    small: pd.DataFrame,
) -> tuple[pd.Series, pd.Series]:
    """Return daily small/large crowding series over the aligned history."""
    common_dates = large.index.intersection(small.index).sort_values()
    large_c = large.loc[common_dates, "close"].to_numpy(dtype=float)
    small_c = small.loc[common_dates, "close"].to_numpy(dtype=float)
    large_a = large.loc[common_dates, "amount"].to_numpy(dtype=float)
    small_a = small.loc[common_dates, "amount"].to_numpy(dtype=float)
    n = len(common_dates)

    def rolling_momentum(prices: np.ndarray, window: int) -> np.ndarray:
        mom = np.full(n, np.nan)
        mom[window:] = prices[window:] / prices[:-window] - 1.0
        return mom

    momentum_diff: dict[int, np.ndarray] = {}
    for w in MOMENTUM_WINDOWS:
        momentum_diff[w] = rolling_momentum(small_c, w) - rolling_momentum(large_c, w)

    turnover = small_a / large_a
    turnover_rolling: dict[int, np.ndarray] = {}
    for w in MOMENTUM_WINDOWS:
        cumsum = np.cumsum(np.insert(turnover, 0, 0.0))
        rolling = np.full(n, np.nan)
        rolling[w - 1 :] = (cumsum[w:] - cumsum[:-w]) / w
        turnover_rolling[w] = rolling

    momentum_pct: dict[int, np.ndarray] = {}
    turnover_pct: dict[int, np.ndarray] = {}
    for w in MOMENTUM_WINDOWS:
        diff = momentum_diff[w]
        pct = np.full(n, np.nan)
        for i in range(w, n):
            hist = diff[w : i + 1]
            pct[i] = float(np.mean(hist <= diff[i]))
        momentum_pct[w] = pct

        rolling = turnover_rolling[w]
        pct_t = np.full(n, np.nan)
        for i in range(w, n):
            hist_t = rolling[w : i + 1]
            pct_t[i] = float(np.mean(hist_t <= rolling[i]))
        turnover_pct[w] = pct_t

    small_series = np.full(n, np.nan)
    large_series = np.full(n, np.nan)
    for i in range(max(MOMENTUM_WINDOWS), n):
        mom_s = np.array([momentum_pct[w][i] for w in MOMENTUM_WINDOWS])
        turn_s = np.array([turnover_pct[w][i] for w in MOMENTUM_WINDOWS])
        small_series[i] = (_top3_average(mom_s) + _top3_average(turn_s)) / 2
        large_series[i] = (_top3_average(1.0 - mom_s) + _top3_average(1.0 - turn_s)) / 2

    return (
        pd.Series(small_series, index=common_dates),
        pd.Series(large_series, index=common_dates),
    )


def compute_signal(
    large: pd.DataFrame,
    small: pd.DataFrame,
    as_of: str | None = None,
    *,
    expected_through: str | None = None,
) -> dict[str, object]:
    """Return the latest crowding and timing signal as a snapshot dict.

    ``as_of`` is a research/backfill cutoff. ``expected_through`` is a
    production freshness contract: the aligned source data must reach that
    date, and the snapshot is cut off there when no explicit ``as_of`` is
    supplied.
    """
    small_series, large_series = _crowding_series(large, small)
    if small_series.empty:
        raise ValueError("no aligned index data for size-style computation")

    crowding = pd.DataFrame({"small": small_series, "large": large_series}).dropna()
    if expected_through:
        expected_ts = _parse_timestamp(expected_through, "expected-through").normalize()
        available_at_cutoff = crowding.loc[:expected_ts]
        available_through = (
            _parse_timestamp(
                available_at_cutoff.index.max(), "latest valid crowding date"
            ).normalize()
            if not available_at_cutoff.empty
            else None
        )
        if available_through is None or available_through < expected_ts:
            actual = f"{available_through:%Y-%m-%d}" if available_through is not None else "none"
            raise ValueError(
                f"size-style data is stale: actual={actual}, expected={expected_ts:%Y-%m-%d}"
            )

    cutoff = as_of or expected_through
    if cutoff:
        cutoff_ts = _parse_timestamp(cutoff, "as-of cutoff").normalize()
        crowding = crowding.loc[:cutoff_ts]
    if len(crowding) < CROWDING_LOOKBACK_DAYS:
        raise ValueError(
            "insufficient history for crowding computation: "
            f"need {CROWDING_LOOKBACK_DAYS} valid observations, got {len(crowding)}"
        )

    last_idx = crowding.index[-1]
    recent = crowding.tail(CROWDING_LOOKBACK_DAYS)
    high = bool(
        (recent["small"] > CROWDING_THRESHOLDS["small_high"]).any()
        or (recent["large"] < CROWDING_THRESHOLDS["large_high"]).any()
    )
    crowding_zone = "high_crowding" if high else "low_crowding"

    small_crowding = float(crowding.loc[last_idx, "small"])
    large_crowding = float(crowding.loc[last_idx, "large"])

    # Keep every returned time series bounded by the snapshot date so a
    # backdated chart cannot leak future observations.
    small_series = small_series.loc[:last_idx]
    large_series = large_series.loc[:last_idx]

    # Timing signal from dual MA on relative strength, using data up to last_idx.
    common_dates = small_series.index
    large_c = large.loc[common_dates, "close"]
    small_c = small.loc[common_dates, "close"]
    relative_strength = large_c / small_c
    if crowding_zone == "high_crowding":
        short_w, long_w = 5, 20
    else:
        short_w, long_w = 20, 60
    short_ma = relative_strength.rolling(short_w).mean().iloc[-1]
    long_ma = relative_strength.rolling(long_w).mean().iloc[-1]
    if np.isnan(short_ma) or np.isnan(long_ma):
        signal = "insufficient"
    else:
        signal = "large_cap" if short_ma > long_ma else "small_cap"

    return {
        "as_of": last_idx.date(),
        "small_crowding": small_crowding,
        "large_crowding": large_crowding,
        "crowding_zone": crowding_zone,
        "signal": signal,
        "short_window": short_w,
        "long_window": long_w,
        "n_days": len(small_series),
        "small_series": small_series,
        "large_series": large_series,
        "relative_strength": relative_strength,
    }


def load_owner_artifact(
    path: str | Path, *, expected_through: str | None = None
) -> dict[str, object]:
    """Reconstruct the report snapshot from the research-owned artifact."""
    payload = load_weekly_analysis_artifact(
        Path(path), artifact_type="size_style_weekly", expected_as_of=expected_through
    )
    rows = pd.DataFrame(payload["series"])
    dates = pd.to_datetime(rows.pop("date"))
    snapshot = dict(payload["snapshot"])
    snapshot["as_of"] = pd.Timestamp(payload["as_of"]).date()
    snapshot["small_series"] = pd.Series(rows["small"].to_numpy(), index=dates)
    snapshot["large_series"] = pd.Series(rows["large"].to_numpy(), index=dates)
    snapshot["relative_strength"] = pd.Series(rows["relative_strength"].to_numpy(), index=dates)
    snapshot["n_days"] = len(rows)
    return snapshot


def render_markdown(snapshot: dict[str, object]) -> str:
    zone_label = "高拥挤" if snapshot["crowding_zone"] == "high_crowding" else "低拥挤"
    signal_key = str(snapshot["signal"])
    signal_label = {
        "large_cap": "大盘占优",
        "small_cap": "小盘占优",
        "insufficient": "数据不足",
    }[signal_key]
    direction_line = (
        "方向信号：数据不足。"
        if signal_key == "insufficient"
        else (
            f"方向信号：{signal_label}（采用 {snapshot['short_window']} 日和 "
            f"{snapshot['long_window']} 日均线）。"
        )
    )
    lines = [
        "## 大小盘因子（风格）",
        f"数据截至 {snapshot['as_of']:%Y-%m-%d}",
        "",
        "### 01 当前状态",
        "",
        f"拥挤区间：{zone_label}。",
        f"- 小盘拥挤度：{snapshot['small_crowding']:.3f}",
        f"- 大盘拥挤度：{snapshot['large_crowding']:.3f}。低于 0.10 时触发小盘高拥挤。",
        "",
        direction_line,
        "",
        "### 02 证据怎么读",
        "",
        "拥挤程度用于选择均线周期。高拥挤时采用 5 日和 20 日均线，及时观察风格变化。"
        "低拥挤时采用 20 日和 60 日均线，侧重观察中期趋势。",
        "",
        "方向由沪深 300 与中证 1000 的相对强弱决定。短期均线高于长期均线时，大盘占优。"
        "其余情况下，小盘占优。拥挤程度只影响均线周期。",
        "",
        "### 04 下周观察",
        "",
        "- 观察相对强弱短均线是否跌破长均线。",
        "- 观察近 20 日拥挤证据是否回落至 0.90 以下。",
        "",
        "本信号用于观察市场风格，不构成交易建议。",
        "",
    ]
    return "\n".join(lines)


def _prepare_chart_data(
    snapshot: dict[str, object], lookback_days: int
) -> tuple[pd.Timestamp, pd.DataFrame, pd.DataFrame, int, int]:
    small_series = snapshot["small_series"]
    large_series = snapshot["large_series"]
    relative_strength = snapshot["relative_strength"]
    small_series = small_series if isinstance(small_series, pd.Series) else pd.Series(dtype=float)
    large_series = large_series if isinstance(large_series, pd.Series) else pd.Series(dtype=float)
    relative_strength = (
        relative_strength if isinstance(relative_strength, pd.Series) else pd.Series(dtype=float)
    )
    as_of = _parse_timestamp(snapshot["as_of"], "snapshot as-of")
    recent = (
        pd.DataFrame(
            {
                "small": small_series.loc[:as_of],
                "large": large_series.loc[:as_of],
                "large_neglect_confirmation": 1.0 - large_series.loc[:as_of],
            }
        )
        .dropna()
        .tail(lookback_days)
    )
    short_window = cast(int, snapshot["short_window"])
    long_window = cast(int, snapshot["long_window"])
    strength = pd.DataFrame(
        {
            "relative_strength": relative_strength.loc[:as_of],
            "short_ma": relative_strength.loc[:as_of].rolling(short_window).mean(),
            "long_ma": relative_strength.loc[:as_of].rolling(long_window).mean(),
        }
    ).tail(lookback_days)
    if recent.empty or strength["relative_strength"].dropna().empty:
        raise ValueError("snapshot does not contain chartable size-style history")
    return as_of, recent, strength, short_window, long_window


def _add_chart_summary(
    fig: Any,
    snapshot: dict[str, object],
    short_window: int,
    long_window: int,
    *,
    theme: Any,
    font: Any,
    heavy_font: Any,
) -> None:
    zone_label = "高拥挤" if snapshot["crowding_zone"] == "high_crowding" else "低拥挤"
    signal_key = str(snapshot["signal"])
    signal_label = {
        "large_cap": "大盘占优",
        "small_cap": "小盘占优",
        "insufficient": "数据不足",
    }[signal_key]
    signal_color = theme.ACCENT if signal_key == "large_cap" else theme.UP
    metric_columns = (
        (0.055, "CURRENT · 风格方向", signal_label, signal_color),
        (0.405, "CURRENT · 拥挤状态", zone_label, theme.YELLOW),
        (0.745, "EVIDENCE · 均线", f"{short_window} / {long_window} 日", theme.FG),
    )
    for x, label, value, color in metric_columns:
        fig.text(x, 0.795, label, fontsize=8, color=theme.MUTED, fontproperties=font)
        fig.text(
            x,
            0.76,
            value,
            fontsize=15,
            color=color,
            fontweight="bold",
            fontproperties=heavy_font,
        )


def _plot_crowding_panel(
    ax: Any,
    recent: pd.DataFrame,
    lookback_days: int,
    *,
    theme: Any,
    font: Any,
    heavy_font: Any,
) -> None:
    ax.axhspan(CROWDING_THRESHOLDS["small_high"], 1, color=theme.UP, alpha=0.07, linewidth=0)
    ax.plot(recent.index, recent["small"], color=theme.UP, linewidth=1.9, label="小盘拥挤度")
    ax.plot(
        recent.index,
        recent["large_neglect_confirmation"],
        color=theme.ACCENT,
        linewidth=1.9,
        label="大盘冷清确认（1−大盘拥挤度）",
    )
    ax.axhline(
        CROWDING_THRESHOLDS["small_high"],
        color=theme.UP,
        linestyle="--",
        alpha=0.55,
        linewidth=0.9,
    )
    last_date = recent.index[-1]
    for column, color, offset in (
        ("small", theme.UP, 10),
        ("large_neglect_confirmation", theme.ACCENT, -14),
    ):
        value = float(recent[column].iloc[-1])
        ax.scatter(last_date, value, color=color, s=30, zorder=4)
        ax.annotate(
            f"{value:.2f}",
            (last_date, value),
            xytext=(-4, offset),
            textcoords="offset points",
            ha="right",
            color=color,
            fontsize=8,
            fontweight="bold",
        )
    ax.set_title(
        f"02 · 拥挤风险｜近 {min(lookback_days, len(recent))} 个交易日",
        loc="left",
        color=theme.FG,
        fontsize=11,
        fontweight="bold",
        fontproperties=heavy_font,
    )
    ax.text(
        1,
        1.02,
        "任一证据近 20 日 > 0.90，即进入高拥挤区间",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=7.5,
        color=theme.MUTED,
        fontproperties=font,
    )
    ax.set_ylim(0, 1)
    ax.set_ylabel("历史分位", color=theme.MUTED, fontsize=8, fontproperties=font)
    ax.legend(loc="upper left", ncol=2, frameon=False, fontsize=8, prop=font)


def _plot_strength_panel(
    ax: Any,
    strength: pd.DataFrame,
    short_window: int,
    long_window: int,
    *,
    theme: Any,
    font: Any,
    heavy_font: Any,
) -> None:
    ax.plot(
        strength.index,
        strength["relative_strength"],
        color=theme.FLAT,
        linewidth=1.1,
        alpha=0.8,
        label="沪深300 / 中证1000",
    )
    ax.plot(
        strength.index,
        strength["short_ma"],
        color=theme.ACCENT,
        linewidth=1.8,
        label=f"{short_window} 日均线",
    )
    ax.plot(
        strength.index,
        strength["long_ma"],
        color=theme.YELLOW,
        linewidth=1.8,
        label=f"{long_window} 日均线",
    )
    ax.set_title(
        "01 · 方向｜沪深300 ÷ 中证1000",
        loc="left",
        color=theme.FG,
        fontsize=11,
        fontweight="bold",
        fontproperties=heavy_font,
    )
    ax.text(
        1,
        1.02,
        "短均线高于长均线＝大盘占优",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=7.5,
        color=theme.MUTED,
        fontproperties=font,
    )
    ax.legend(loc="upper left", ncol=3, frameon=False, fontsize=7.5, prop=font)


def generate_chart(
    snapshot: dict[str, object],
    out_path: str | Path,
    lookback_days: int = 120,
) -> Path:
    """Render a mobile-first decision card explaining the current signal."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    from a_share_daily.charts.theme import (
        LIGHT,
        add_report_header,
        cjk,
        cjk_heavy,
        style_plot_axes,
    )

    as_of, recent, strength, short_window, long_window = _prepare_chart_data(
        snapshot, lookback_days
    )

    LIGHT.apply()
    fig = plt.figure(figsize=(8, 10), dpi=150, facecolor=LIGHT.BG)
    add_report_header(
        fig,
        title="大小盘风格｜拥挤与趋势",
        kicker="市场风格周报 · SIZE STYLE",
        subtitle=f"沪深300 / 中证1000 · 数据截至 {as_of:%Y-%m-%d}",
    )
    _add_chart_summary(
        fig,
        snapshot,
        short_window,
        long_window,
        theme=LIGHT,
        font=cjk,
        heavy_font=cjk_heavy,
    )

    grid = fig.add_gridspec(
        10,
        1,
        left=0.075,
        right=0.95,
        top=0.70,
        bottom=0.085,
        hspace=1.4,
    )
    strength_ax = fig.add_subplot(grid[:6, 0])
    crowding_ax = fig.add_subplot(grid[6:, 0])
    style_plot_axes(crowding_ax)
    style_plot_axes(strength_ax)
    _plot_crowding_panel(
        crowding_ax,
        recent,
        lookback_days,
        theme=LIGHT,
        font=cjk,
        heavy_font=cjk_heavy,
    )
    _plot_strength_panel(
        strength_ax,
        strength,
        short_window,
        long_window,
        theme=LIGHT,
        font=cjk,
        heavy_font=cjk_heavy,
    )

    for axis in (crowding_ax, strength_ax):
        axis.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        axis.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        axis.tick_params(colors=LIGHT.MUTED, labelsize=8)

    fig.text(
        0.075,
        0.035,
        "SIZE｜方向由均线交叉决定，拥挤程度决定观察周期｜仅作风格风险参考",
        fontsize=7.2,
        color=LIGHT.MUTED,
        fontproperties=cjk,
    )
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, facecolor=LIGHT.BG, edgecolor="none")
    plt.close(fig)
    return out


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Size-style weekly snapshot report")
    parser.add_argument("--out", help="Markdown output path (default: stdout)")
    parser.add_argument("--chart-out", help="Crowding chart PNG output path")
    parser.add_argument("--expected-through", help="Required data cutoff date, YYYYMMDD")
    parser.add_argument(
        "--artifact",
        help="Research-owned size/style artifact; when set, no research calculation runs here",
    )
    parser.add_argument(
        "--small-index",
        default=DEFAULT_SMALL_INDEX,
        help=f"Small-cap index code (default: {DEFAULT_SMALL_INDEX})",
    )
    parser.add_argument(
        "--large-index",
        default=DEFAULT_LARGE_INDEX,
        help=f"Large-cap index code (default: {DEFAULT_LARGE_INDEX})",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s - %(message)s")

    if args.artifact:
        snapshot = load_owner_artifact(args.artifact, expected_through=args.expected_through)
    else:
        large = load_index_data(args.large_index)
        small = load_index_data(args.small_index)
        try:
            snapshot = compute_signal(
                large,
                small,
                expected_through=args.expected_through,
            )
        except ValueError as exc:
            raise SystemExit(f"size-style report failed: {exc}") from exc
    report = render_markdown(snapshot)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
        logger.info("Report written to %s", out_path)
    else:
        print(report)

    if args.chart_out:
        chart = generate_chart(snapshot, args.chart_out)
        logger.info("Chart written to %s", chart)


if __name__ == "__main__":
    main()
