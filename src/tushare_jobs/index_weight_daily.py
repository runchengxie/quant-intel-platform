"""Daily expansion of index_weight snapshots with optional drift weights.

Migrated from tushare-email-fetch/scripts/index_weight_utils.py.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import cast

import pandas as pd


def _ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def expand_index_weight_daily(
    df: pd.DataFrame,
    trade_dates: list[date],
    output_path: Path,
    *,
    prices: pd.DataFrame | None = None,
) -> int:
    """Expand index_weight snapshots into daily rows with optional drift weights.

    - Base behaviour: forward-fill snapshots until the next rebalance day.
    - If *prices* is provided (columns: ts_code, trade_date, close), also
      compute drift weights: w_i(t) ∝ w_i(s) × P_i(t) / P_i(s), normalized daily.
    """
    _ensure_parent_dir(output_path)

    if df.empty:
        pd.DataFrame(
            columns=pd.Index(
                [
                    "trade_date",
                    "snapshot_date",
                    "index_code",
                    "con_code",
                    "weight",
                    "drift_weight",
                ]
            )
        ).to_csv(output_path, index=False)
        return 0

    df = df.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"].astype(str), format="%Y%m%d").dt.date
    trade_dates = sorted(set(trade_dates))
    base_cols = [col for col in df.columns if col != "trade_date"]

    price_panel = None
    if prices is not None and not prices.empty:
        price_panel = _prepare_price_panel(prices, trade_dates)

    frames = []
    for _, g in df.groupby("index_code"):
        g = g.sort_values("trade_date")
        snap_dates = g["trade_date"].drop_duplicates().tolist()
        for i, snap_date in enumerate(snap_dates):
            next_snap = snap_dates[i + 1] if i + 1 < len(snap_dates) else None
            segment_days = [
                d for d in trade_dates if d >= snap_date and (next_snap is None or d < next_snap)
            ]
            if not segment_days:
                continue
            snap_rows = cast(pd.DataFrame, g[g["trade_date"] == snap_date][base_cols].copy())
            snap_rows.insert(0, "snapshot_date", snap_date)
            repeated = pd.concat(
                [snap_rows.assign(trade_date=d) for d in segment_days],
                ignore_index=True,
            )

            if price_panel is not None:
                drift = _compute_drift_weights(
                    price_panel=price_panel,
                    snapshot_date=snap_date,
                    segment_days=segment_days,
                    snapshot_rows=snap_rows,
                )
                if drift is not None and not drift.empty:
                    repeated = repeated.merge(drift, on=["trade_date", "con_code"], how="left")

            frames.append(repeated)

    if frames:
        out_df = pd.concat(frames, ignore_index=True)
    else:
        out_df = pd.DataFrame(
            columns=pd.Index(["snapshot_date"] + base_cols + ["trade_date", "drift_weight"])
        )

    if "drift_weight" not in out_df.columns:
        out_df["drift_weight"] = pd.NA

    out_cols = (
        ["trade_date", "snapshot_date"]
        + [col for col in base_cols if col != "snapshot_date"]
        + ["drift_weight"]
    )
    out_df = cast(pd.DataFrame, out_df[out_cols])
    out_df.to_csv(output_path, index=False)
    return len(out_df)


def _prepare_price_panel(prices: pd.DataFrame, trade_dates: list[date]) -> pd.DataFrame | None:
    """Pivot ts_code × trade_date → close, forward-filled by trading day order."""
    if prices.empty:
        return None

    prices = prices.copy()
    prices["trade_date"] = pd.to_datetime(prices["trade_date"].astype(str), format="%Y%m%d").dt.date
    prices = prices.dropna(subset=["trade_date", "ts_code", "close"])
    pivot = prices.pivot(index="trade_date", columns="ts_code", values="close")
    return pivot.reindex(sorted(set(trade_dates))).sort_index().ffill()


def _compute_drift_weights(
    *,
    price_panel: pd.DataFrame,
    snapshot_date: date,
    segment_days: list[date],
    snapshot_rows: pd.DataFrame,
) -> pd.DataFrame | None:
    """Compute drift weights from price movements, returning (trade_date, con_code, drift_weight)."""
    codes = snapshot_rows["con_code"].tolist()
    weights = snapshot_rows.set_index("con_code")["weight"].astype(float)

    try:
        base_prices = price_panel.loc[snapshot_date, codes]
    except KeyError:
        return None

    base_prices = base_prices.astype(float)
    valid_codes = base_prices.dropna().index
    if len(valid_codes) == 0:
        return None

    weights = weights.reindex(valid_codes).dropna()
    if weights.empty:
        return None

    base_prices = base_prices.loc[weights.index]
    segment_prices = price_panel.loc[segment_days, weights.index]

    rel = segment_prices.divide(base_prices)
    weighted = rel.multiply(weights, axis=1)
    denom = weighted.sum(axis=1)
    denom = denom.replace(0, pd.NA)
    drift = weighted.div(denom, axis=0)

    drift.columns.name = None
    return (
        drift.stack()
        .rename("drift_weight")
        .reset_index()
        .rename(columns={"level_0": "trade_date", "level_1": "con_code"})
    )
