"""Technical-analysis indicators shared by BTC and XAU reports."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import cast

import numpy as np
import pandas as pd


def moving_average(values: Sequence[float], window: int) -> list[float]:
    """Simple moving average with NaN padding until the window is filled."""
    if window <= 0:
        raise ValueError("window must be > 0")
    out = [math.nan] * len(values)
    window_sum = 0.0
    for idx, value in enumerate(values):
        window_sum += value
        if idx >= window:
            window_sum -= values[idx - window]
        if idx >= window - 1:
            out[idx] = window_sum / window
    return out


def relative_strength_index(values: Sequence[float], window: int) -> list[float]:
    """Compute RSI with Wilder smoothing."""
    if window <= 0:
        raise ValueError("window must be > 0")
    out = [math.nan] * len(values)
    if len(values) <= window:
        return out

    gains: list[float] = []
    losses: list[float] = []
    for idx in range(1, window + 1):
        change = values[idx] - values[idx - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    avg_gain = sum(gains) / window
    avg_loss = sum(losses) / window
    if avg_loss == 0 and avg_gain == 0:
        out[window] = 50.0
    elif avg_loss == 0:
        out[window] = 100.0
    else:
        rs = avg_gain / avg_loss
        out[window] = 100.0 - (100.0 / (1.0 + rs))

    for idx in range(window + 1, len(values)):
        change = values[idx] - values[idx - 1]
        gain = max(change, 0.0)
        loss = max(-change, 0.0)
        avg_gain = ((avg_gain * (window - 1)) + gain) / window
        avg_loss = ((avg_loss * (window - 1)) + loss) / window
        if avg_loss == 0 and avg_gain == 0:
            out[idx] = 50.0
        elif avg_loss == 0:
            out[idx] = 100.0
        else:
            rs = avg_gain / avg_loss
            out[idx] = 100.0 - (100.0 / (1.0 + rs))
    return out


def average_true_range(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    window: int,
) -> list[float]:
    """Average true range using a simple moving average of true ranges."""
    if window <= 0:
        raise ValueError("window must be > 0")
    if not (len(highs) == len(lows) == len(closes)):
        raise ValueError("highs, lows, and closes must have the same length")
    out = [math.nan] * len(closes)
    if not closes:
        return out

    tr_values: list[float] = []
    window_sum = 0.0
    for idx, _close in enumerate(closes):
        if idx == 0:
            true_range = highs[idx] - lows[idx]
        else:
            prev_close = closes[idx - 1]
            true_range = max(
                highs[idx] - lows[idx],
                abs(highs[idx] - prev_close),
                abs(lows[idx] - prev_close),
            )
        tr_values.append(true_range)
        window_sum += true_range
        if idx >= window:
            window_sum -= tr_values[idx - window]
        if idx >= window - 1:
            out[idx] = window_sum / window
    return out


def classic_pivots(high: float, low: float, close: float) -> tuple[float, ...]:
    """Return PP/R1/S1/R2/S2/R3/S3 classic pivot levels."""
    pp = (high + low + close) / 3
    r1 = 2 * pp - low
    s1 = 2 * pp - high
    r2 = pp + (high - low)
    s2 = pp - (high - low)
    r3 = high + 2 * (pp - low)
    s3 = low - 2 * (high - pp)
    return pp, r1, s1, r2, s2, r3, s3


def pandas_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """RSI implementation preserving the existing BTC pandas semantics."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / (avg_loss.replace(0, np.nan))
    return cast(pd.Series, 100 - (100 / (1 + rs)))


def pandas_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """ATR implementation preserving the existing BTC pandas semantics."""
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return cast(pd.Series, tr.rolling(window=period, min_periods=1).mean())
