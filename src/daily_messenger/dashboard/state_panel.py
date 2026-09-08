"""Build the optional market-state panel used by the dashboard."""

from __future__ import annotations

import argparse
import io
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pandas as pd
import requests

from daily_messenger.dashboard.payload import DEFAULT_STATE_PANEL_NAME, OUT_DIR
from daily_messenger.etl.fetchers.cboe_putcall import CSV_SOURCES as CBOE_PUTCALL_SOURCES
from daily_messenger.etl.fetchers.fred import fetch_observations

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
DEFAULT_PERIOD: str = "10y"
DEFAULT_TIMEOUT: int = 20
DEFAULT_BREADTH_BATCH_SIZE: int = 80
DEFAULT_BREADTH_MODE: str = "sample"
DEFAULT_OUTPUT: Path = OUT_DIR / DEFAULT_STATE_PANEL_NAME

FRED_SERIES = {
    "vix": "VIXCLS",
    "ten_year_yield": "DGS10",
}
CBOE_INDEX_URLS = {
    "vix_cboe": "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv",
    "vvix": "https://cdn.cboe.com/api/global/us_indices/daily_prices/VVIX_History.csv",
}
YFINANCE_PRICE_COLUMNS = {
    "SPY": "spy_close",
    "QQQ": "qqq_close",
    "RSP": "rsp_close",
    "^GSPC": "sp500_close",
    "^NDX": "ndx_close",
    "^TNX": "ten_year_yield_yf",
}
WIKI_UNIVERSE_URLS = {
    "spx": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
    "ndx": "https://en.wikipedia.org/wiki/Nasdaq-100",
}
BREADTH_SAMPLE_SYMBOLS = {
    "spx": [
        "AAPL",
        "MSFT",
        "NVDA",
        "AMZN",
        "GOOGL",
        "GOOG",
        "META",
        "BRK-B",
        "AVGO",
        "TSLA",
        "JPM",
        "LLY",
        "V",
        "XOM",
        "UNH",
        "MA",
        "COST",
        "WMT",
        "NFLX",
        "PG",
        "HD",
        "JNJ",
        "ABBV",
        "BAC",
        "KO",
        "PM",
        "CRM",
        "ORCL",
        "AMD",
        "CVX",
        "CSCO",
        "IBM",
        "GE",
        "MRK",
        "WFC",
        "MCD",
        "ABT",
        "LIN",
        "DIS",
        "INTU",
        "T",
        "VZ",
        "PEP",
        "TXN",
        "QCOM",
        "NOW",
        "AMGN",
        "CAT",
        "GS",
        "RTX",
    ],
    "ndx": [
        "AAPL",
        "MSFT",
        "NVDA",
        "AMZN",
        "AVGO",
        "META",
        "TSLA",
        "GOOGL",
        "GOOG",
        "COST",
        "NFLX",
        "AMD",
        "CSCO",
        "TMUS",
        "PEP",
        "LIN",
        "ISRG",
        "INTU",
        "QCOM",
        "TXN",
        "BKNG",
        "AMGN",
        "AMAT",
        "ADI",
        "PANW",
        "MU",
        "LRCX",
        "KLAC",
        "GILD",
        "ADP",
        "MELI",
        "ASML",
        "ARM",
        "SHOP",
        "ABNB",
        "CRWD",
        "CDNS",
        "SNPS",
        "MAR",
        "REGN",
        "MDLZ",
        "CEG",
        "ORLY",
        "CSX",
        "PYPL",
        "NXPI",
        "PCAR",
        "MNST",
        "FTNT",
        "ADBE",
    ],
}


@dataclass(frozen=True)
class StatePanelBuildResult:
    path: Path
    rows: int
    columns: list[str]
    warnings: list[str]


def _request_text(url: str, *, timeout: int) -> str:
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    response.raise_for_status()
    return response.text


def _empty_frame(columns: Sequence[str] = ("date",)) -> pd.DataFrame:
    return pd.DataFrame(columns=pd.Index(list(columns)))


def _select_columns(frame: pd.DataFrame, columns: Sequence[str]) -> pd.DataFrame:
    return cast(pd.DataFrame, frame.loc[:, list(columns)])


def _numeric_series(frame: pd.DataFrame, column: str) -> pd.Series:
    return cast(pd.Series, pd.to_numeric(frame[column], errors="coerce"))


def _midnight_timestamp(value: Any) -> pd.Timestamp | Any:
    timestamp = pd.Timestamp(value)
    if str(timestamp) == "NaT":
        return pd.NaT
    return pd.Timestamp(
        year=int(timestamp.year), month=int(timestamp.month), day=int(timestamp.day)
    )


def _date_string(value: object) -> str | None:
    timestamp = _midnight_timestamp(value)
    if str(timestamp) == "NaT":
        return None
    return str(cast(pd.Timestamp, timestamp).date())


def _normalize_dates(frame: pd.DataFrame, column: str = "date") -> pd.DataFrame:
    if frame.empty or column not in frame.columns:
        return _empty_frame()
    normalized = frame.copy()
    normalized["date"] = [_midnight_timestamp(value) for value in normalized[column].to_list()]
    normalized = normalized.dropna(subset=["date"])
    return normalized.drop_duplicates(subset=["date"], keep="last").sort_values("date")


def _filter_start(frame: pd.DataFrame, start: str | None) -> pd.DataFrame:
    if not start or frame.empty:
        return frame
    start_ts = _midnight_timestamp(start)
    if pd.isna(start_ts):
        raise ValueError(f"无法解析开始日期：{start}")
    return frame.loc[frame["date"] >= start_ts].copy()


def _merge_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    clean_frames = [frame for frame in frames if not frame.empty]
    if not clean_frames:
        return _empty_frame()
    merged = clean_frames[0]
    for frame in clean_frames[1:]:
        merged = merged.merge(frame, on="date", how="outer")
    return merged.sort_values("date").reset_index(drop=True)


def _safe_fetch_frame(
    label: str, func: Callable[[], pd.DataFrame]
) -> tuple[pd.DataFrame, str | None]:
    try:
        return func(), None
    except Exception as exc:  # noqa: BLE001
        return _empty_frame(), f"{label}: {exc}"


def fetch_fred_series(*, start: str | None = None, timeout: int = DEFAULT_TIMEOUT) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for column, series_id in FRED_SERIES.items():
        observations = fetch_observations(series_id, start=start, timeout=timeout)
        frame = pd.DataFrame(
            ({"date": observation.date, column: observation.value} for observation in observations),
            columns=pd.Index(["date", column]),
        )
        frame = _normalize_dates(_select_columns(frame, ("date", column)))
        frames.append(frame)
    return _merge_frames(frames)


def fetch_cboe_indices(*, start: str | None = None, timeout: int = DEFAULT_TIMEOUT) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for column, url in CBOE_INDEX_URLS.items():
        raw = pd.read_csv(io.StringIO(_request_text(url, timeout=timeout)))
        if "DATE" not in raw.columns:
            continue
        value_column = (
            "CLOSE" if "CLOSE" in raw.columns else "VVIX" if "VVIX" in raw.columns else ""
        )
        if not value_column:
            continue
        frame = raw.rename(columns={"DATE": "date", value_column: column})
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame = _normalize_dates(_select_columns(frame, ("date", column)))
        frames.append(_filter_start(frame, start))
    return _merge_frames(frames)


def _read_cboe_putcall_csv(text: str, column: str) -> pd.DataFrame:
    lines = text.splitlines()
    header_index = next(
        (idx for idx, line in enumerate(lines) if line.upper().startswith("DATE,")),
        None,
    )
    if header_index is None:
        return _empty_frame(("date", column))
    raw = pd.read_csv(io.StringIO("\n".join(lines[header_index:])))
    if "DATE" not in raw.columns or "P/C Ratio" not in raw.columns:
        return _empty_frame(("date", column))
    frame = raw.rename(columns={"DATE": "date", "P/C Ratio": column})
    frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return _normalize_dates(_select_columns(frame, ("date", column)))


def fetch_put_call_history(
    *, start: str | None = None, timeout: int = DEFAULT_TIMEOUT
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for key, url in CBOE_PUTCALL_SOURCES.items():
        column = f"put_call_{key}"
        frame = _read_cboe_putcall_csv(_request_text(url, timeout=timeout), column)
        frames.append(_filter_start(frame, start))
    return _merge_frames(frames)


def _extract_yfinance_close(raw: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    if raw.empty:
        return _empty_frame()
    if isinstance(raw.columns, pd.MultiIndex):
        close = cast(
            pd.DataFrame,
            raw["Close"] if "Close" in raw.columns.get_level_values(0) else raw["Adj Close"],
        )
    else:
        value_column = (
            "Close" if "Close" in raw.columns else "Adj Close" if "Adj Close" in raw.columns else ""
        )
        if not value_column:
            return _empty_frame()
        close = _select_columns(raw, (value_column,)).rename(columns={value_column: tickers[0]})

    close = close.reset_index()
    date_column = (
        "Date" if "Date" in close.columns else "Datetime" if "Datetime" in close.columns else ""
    )
    if not date_column:
        return _empty_frame()

    close = close.rename(columns={date_column: "date"})
    selected: dict[str, Any] = {}
    for ticker in tickers:
        if ticker in close.columns:
            selected[YFINANCE_PRICE_COLUMNS.get(ticker, ticker)] = pd.to_numeric(
                close[ticker], errors="coerce"
            )
    if not selected:
        return _empty_frame()
    return _normalize_dates(pd.DataFrame({"date": close["date"], **selected}))


def fetch_yfinance_prices(
    *,
    period: str = DEFAULT_PERIOD,
    start: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> pd.DataFrame:
    del timeout
    import yfinance as yf

    tickers = list(YFINANCE_PRICE_COLUMNS)
    if start:
        raw = yf.download(
            tickers=tickers,
            auto_adjust=True,
            progress=False,
            threads=True,
            start=start,
        )
    else:
        raw = yf.download(
            tickers=tickers,
            auto_adjust=True,
            progress=False,
            threads=True,
            period=period,
        )
    return _extract_yfinance_close(cast(pd.DataFrame, raw), tickers)


def _symbol_from_columns(frame: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    for column in candidates:
        if column in frame.columns:
            return column
    return None


def _normalize_yahoo_symbols(symbols: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        ticker = symbol.strip().replace(".", "-")
        if not ticker or ticker in seen:
            continue
        normalized.append(ticker)
        seen.add(ticker)
    return normalized


def fetch_wikipedia_universe(name: str, *, timeout: int = DEFAULT_TIMEOUT) -> list[str]:
    url = WIKI_UNIVERSE_URLS[name]
    tables = pd.read_html(io.StringIO(_request_text(url, timeout=timeout)))
    min_size = 400 if name == "spx" else 90
    for table in tables:
        symbol_column = _symbol_from_columns(table, ("Symbol", "Ticker"))
        if symbol_column and len(table) >= min_size:
            return _normalize_yahoo_symbols(table[symbol_column].dropna().astype(str).tolist())
    return []


def _extract_close_for_any_tickers(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty or not isinstance(raw.columns, pd.MultiIndex):
        return _empty_frame(())
    if "Close" in raw.columns.get_level_values(0):
        close = cast(pd.DataFrame, raw["Close"])
    elif "Adj Close" in raw.columns.get_level_values(0):
        close = cast(pd.DataFrame, raw["Adj Close"])
    else:
        return _empty_frame(())
    close = close.apply(pd.to_numeric, errors="coerce")
    close.index = pd.Index([_midnight_timestamp(value) for value in close.index])
    close = close.loc[close.index.notna()]
    return close.dropna(how="all")


def _download_close_batch(
    symbols: list[str],
    *,
    period: str,
    start: str | None,
) -> pd.DataFrame:
    import yfinance as yf

    if start:
        raw = yf.download(
            tickers=symbols,
            auto_adjust=True,
            progress=False,
            threads=True,
            start=start,
        )
    else:
        raw = yf.download(
            tickers=symbols,
            auto_adjust=True,
            progress=False,
            threads=True,
            period=period,
        )
    return _extract_close_for_any_tickers(cast(pd.DataFrame, raw))


def _calculate_breadth(close: pd.DataFrame, prefix: str) -> pd.DataFrame:
    if close.empty:
        return _empty_frame()
    rows = pd.DataFrame(index=close.index)
    for window in (20, 50, 200):
        moving_average = close.rolling(window=window, min_periods=window).mean()
        rows[f"{prefix}_above_{window}d_pct"] = close.gt(moving_average).mean(axis=1) * 100
    rows[f"{prefix}_breadth_component_count"] = close.notna().sum(axis=1)
    rows = rows.rename_axis("date").reset_index()
    return _normalize_dates(rows)


def fetch_breadth(
    name: str,
    *,
    period: str = DEFAULT_PERIOD,
    start: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    batch_size: int = DEFAULT_BREADTH_BATCH_SIZE,
    mode: str = DEFAULT_BREADTH_MODE,
) -> pd.DataFrame:
    symbols = (
        fetch_wikipedia_universe(name, timeout=timeout)
        if mode == "full"
        else list(BREADTH_SAMPLE_SYMBOLS[name])
    )
    if not symbols:
        return _empty_frame()

    close_frames: list[pd.DataFrame] = []
    for offset in range(0, len(symbols), batch_size):
        batch = symbols[offset : offset + batch_size]
        try:
            close = _download_close_batch(batch, period=period, start=start)
        except Exception:  # noqa: BLE001
            continue
        if not close.empty:
            close_frames.append(close)
    if not close_frames:
        return _empty_frame()
    combined = pd.concat(close_frames, axis=1).sort_index()
    combined = combined.loc[:, ~combined.columns.duplicated()]
    return _calculate_breadth(combined, name)


def _safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    return numerator.divide(denominator.where(denominator.ne(0)))


def _rolling_zscore(series: pd.Series, window: int = 252) -> pd.Series:
    mean = series.rolling(window=window, min_periods=63).mean()
    std = series.rolling(window=window, min_periods=63).std(ddof=0)
    return (series - mean).divide(std.where(std.ne(0)))


def _clamp_series(series: pd.Series, lower: float, upper: float) -> pd.Series:
    return series.clip(lower=lower, upper=upper)


def _forward_return(series: pd.Series, days: int) -> pd.Series:
    return cast(pd.Series, series.shift(-days).divide(series).subtract(1))


def _enrich_vix_and_yield(enriched: pd.DataFrame) -> None:
    if "vix" not in enriched.columns and "vix_cboe" in enriched.columns:
        enriched["vix"] = enriched["vix_cboe"]
    elif "vix" in enriched.columns and "vix_cboe" in enriched.columns:
        enriched["vix"] = _numeric_series(enriched, "vix").combine_first(
            _numeric_series(enriched, "vix_cboe")
        )

    if "ten_year_yield" not in enriched.columns and "ten_year_yield_yf" in enriched.columns:
        ten_year_yf = _numeric_series(enriched, "ten_year_yield_yf")
        divisor = 10 if ten_year_yf.dropna().median() > 20 else 1
        enriched["ten_year_yield"] = ten_year_yf / divisor

    for column in ("ten_year_yield", "ten_year_yield_yf"):
        if column in enriched.columns:
            enriched[column] = _numeric_series(enriched, column).ffill(limit=5)


def _enrich_vol_structure(enriched: pd.DataFrame) -> None:
    if {"vvix", "vix"}.issubset(enriched.columns):
        enriched["vol_structure"] = (
            _safe_divide(_numeric_series(enriched, "vvix"), _numeric_series(enriched, "vix")) / 3.5
        )


def _enrich_participation(enriched: pd.DataFrame) -> None:
    if {"rsp_close", "spy_close"}.issubset(enriched.columns):
        ratio = _safe_divide(
            _numeric_series(enriched, "rsp_close"),
            _numeric_series(enriched, "spy_close"),
        )
        enriched["rsp_spy_participation_proxy"] = (
            ratio.divide(ratio.rolling(window=63, min_periods=20).mean()) - 1
        )


def _enrich_spy_qqq_features(enriched: pd.DataFrame) -> None:
    for ticker in ("spy", "qqq"):
        close_column = f"{ticker}_close"
        if close_column not in enriched.columns:
            continue
        close = _numeric_series(enriched, close_column)
        enriched[f"{ticker}_high"] = close.cummax()
        enriched[f"{ticker}_52w_high"] = close.rolling(window=252, min_periods=20).max()
        for days in (90, 252, 1260, 2520):
            enriched[f"{ticker}_forward_return_fwd_{days}d"] = _forward_return(close, days)


def _enrich_risk_appetite_score(enriched: pd.DataFrame) -> None:
    score_components: list[pd.Series] = []
    if "vix" in enriched.columns:
        vix_score = 50 + (20 - _numeric_series(enriched, "vix")) * 2.5
        score_components.append(_clamp_series(vix_score, 0, 100))
    if "vol_structure" in enriched.columns:
        vol_score = 50 + (1 - _numeric_series(enriched, "vol_structure")) * 45
        score_components.append(_clamp_series(vol_score, 0, 100))
    if "put_call_equity" in enriched.columns:
        put_call_z = _rolling_zscore(_numeric_series(enriched, "put_call_equity"))
        put_call_score = put_call_z.multiply(-15).add(50)
        score_components.append(_clamp_series(put_call_score, 0, 100))
    if "rsp_spy_participation_proxy" in enriched.columns:
        participation_score = (
            _numeric_series(enriched, "rsp_spy_participation_proxy").multiply(450).add(50)
        )
        score_components.append(_clamp_series(participation_score, 0, 100))

    if score_components:
        component_frame = pd.concat(score_components, axis=1)
        enriched["own_risk_appetite_score"] = component_frame.mean(axis=1, skipna=True)
        enriched["own_risk_appetite_component_count"] = component_frame.notna().sum(axis=1)


def _enrich_valuation_gap(enriched: pd.DataFrame) -> None:
    if {"spy_close", "ten_year_yield"}.issubset(enriched.columns):
        spy = _numeric_series(enriched, "spy_close")
        ten_year = _numeric_series(enriched, "ten_year_yield")
        price_pressure = _rolling_zscore(spy.divide(spy.rolling(window=200, min_periods=60).mean()))
        rate_pressure = _rolling_zscore(ten_year)
        enriched["valuation_rate_gap_proxy"] = price_pressure + rate_pressure * 0.35
        enriched["valuation_rate_gap_component_count"] = (
            pd.concat([price_pressure, rate_pressure], axis=1).notna().sum(axis=1)
        )


def enrich_state_panel(panel: pd.DataFrame) -> pd.DataFrame:
    if panel.empty:
        return _empty_frame()
    enriched = _normalize_dates(panel)
    _enrich_vix_and_yield(enriched)
    _enrich_vol_structure(enriched)
    _enrich_participation(enriched)
    _enrich_spy_qqq_features(enriched)
    _enrich_risk_appetite_score(enriched)
    _enrich_valuation_gap(enriched)

    numeric_columns = [column for column in enriched.columns if column != "date"]
    for column in numeric_columns:
        enriched[column] = _numeric_series(enriched, column)
    enriched = enriched.replace([math.inf, -math.inf], pd.NA)
    enriched["date"] = [_date_string(value) for value in enriched["date"].to_list()]
    return enriched.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)


def build_state_panel(
    *,
    output_path: Path = DEFAULT_OUTPUT,
    period: str = DEFAULT_PERIOD,
    start: str | None = None,
    include_breadth: bool = False,
    breadth_mode: str = DEFAULT_BREADTH_MODE,
    timeout: int = DEFAULT_TIMEOUT,
    min_rows: int = 30,
) -> StatePanelBuildResult:
    source_calls: tuple[tuple[str, Callable[[], pd.DataFrame]], ...] = (
        ("FRED", lambda: fetch_fred_series(start=start, timeout=timeout)),
        ("Cboe volatility", lambda: fetch_cboe_indices(start=start, timeout=timeout)),
        ("Cboe put/call", lambda: fetch_put_call_history(start=start, timeout=timeout)),
        (
            "yfinance prices",
            lambda: fetch_yfinance_prices(period=period, start=start, timeout=timeout),
        ),
    )
    frames: list[pd.DataFrame] = []
    warnings: list[str] = []
    for label, func in source_calls:
        frame, warning = _safe_fetch_frame(label, func)
        frames.append(frame)
        if warning:
            warnings.append(warning)

    if include_breadth:
        for name in ("spx", "ndx"):
            frame, warning = _safe_fetch_frame(
                f"{name.upper()} breadth",
                lambda name=name: fetch_breadth(
                    name,
                    period=period,
                    start=start,
                    timeout=timeout,
                    mode=breadth_mode,
                ),
            )
            frames.append(frame)
            if warning:
                warnings.append(warning)

    panel = enrich_state_panel(_merge_frames(frames))
    non_empty_rows = panel.drop(columns=["date"], errors="ignore").dropna(how="all")
    if len(non_empty_rows) < min_rows:
        raise RuntimeError(f"状态面板有效行数不足，当前 {len(non_empty_rows)} 行")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(output_path, index=False)
    return StatePanelBuildResult(
        path=output_path,
        rows=len(panel),
        columns=[str(column) for column in panel.columns],
        warnings=warnings,
    )


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build local market-state panel for dashboard")
    parser.add_argument(
        "--out",
        default=str(DEFAULT_OUTPUT),
        help=f"Output CSV path (default: out/{DEFAULT_STATE_PANEL_NAME})",
    )
    parser.add_argument(
        "--period",
        default=DEFAULT_PERIOD,
        help=f"yfinance lookback period when --start is not set (default: {DEFAULT_PERIOD})",
    )
    parser.add_argument("--start", help="Start date for historical sources (YYYY-MM-DD)")
    parser.add_argument(
        "--include-breadth",
        action="store_true",
        help="Also fit SPX/NDX 20/50/200D breadth",
    )
    parser.add_argument(
        "--breadth-mode",
        choices=("sample", "full"),
        default=DEFAULT_BREADTH_MODE,
        help="Use core sample constituents or full current public constituents (default: sample)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"HTTP timeout in seconds (default: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--min-rows",
        type=int,
        default=30,
        help="Fail when fewer effective rows are produced (default: 30)",
    )
    args = parser.parse_args(argv)
    result = build_state_panel(
        output_path=Path(args.out),
        period=args.period,
        start=args.start,
        include_breadth=args.include_breadth,
        breadth_mode=args.breadth_mode,
        timeout=args.timeout,
        min_rows=args.min_rows,
    )
    print(f"State panel written to {result.path}")
    print(f"Rows: {result.rows}")
    print(f"Columns: {', '.join(result.columns)}")
    for warning in result.warnings:
        print(f"Warning: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
