"""Fail-closed current-market checks for the weekly 6+4 research basket."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pandas as pd

from .weekly_client_basket import SourcePosition


class WeeklyBasketPreflightError(ValueError):
    """Raised when a weekly basket is unsafe to publish."""


@dataclass(frozen=True)
class WeeklyBasketPreflight:
    report_date: str
    report_week: str
    prior_session: str
    position_count: int
    input_hashes: dict[str, str]


def _date_series(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values.astype(str).str.replace("-", ""), format="%Y%m%d", errors="coerce")


def _symbol_column(frame: pd.DataFrame) -> str:
    for name in ("symbol", "ts_code"):
        if name in frame:
            return name
    raise WeeklyBasketPreflightError("input is missing symbol/ts_code")


def _stable(path: Path) -> None:
    if ".worktrees" in path.resolve().parts:
        raise WeeklyBasketPreflightError("inputs must use a stable production path")


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _calendar_context(path: Path, report: pd.Timestamp) -> tuple[str, pd.Timestamp]:
    calendar = pd.read_parquet(path)
    if not {"cal_date", "is_open"} <= set(calendar):
        raise WeeklyBasketPreflightError("calendar is incomplete")
    dates = _date_series(calendar["cal_date"])
    opens = pd.DatetimeIndex(dates.loc[calendar["is_open"].eq(1)].dropna().unique()).sort_values()
    report_week = report.strftime("%G-W%V")
    week_opens = [date for date in opens if date.strftime("%G-W%V") == report_week]
    if not week_opens or report != week_opens[0]:
        raise WeeklyBasketPreflightError("report date is not the first open day of its week")
    previous = opens[opens < report]
    if previous.empty:
        raise WeeklyBasketPreflightError("calendar has no prior session")
    return report_week, cast(pd.Timestamp, previous[-1])


def _market_snapshot(path: Path, prior: pd.Timestamp) -> tuple[pd.DataFrame, str]:
    market = pd.read_parquet(path)
    symbol_column = _symbol_column(market)
    if not {"trade_date", "amount", "is_st", "is_suspended"} <= set(market):
        raise WeeklyBasketPreflightError("market snapshot is incomplete")
    price_column = next((name for name in ("close", "adj_close", "open") if name in market), None)
    if price_column is None:
        raise WeeklyBasketPreflightError("market snapshot has no price")
    market = market.copy()
    market["trade_date"] = _date_series(market["trade_date"])
    if market["trade_date"].max() != prior:
        raise WeeklyBasketPreflightError("market snapshot is not updated to the prior session")
    market[symbol_column] = market[symbol_column].astype(str).str.upper()
    return market.loc[market["trade_date"].eq(prior)].set_index(symbol_column), price_column


def _validate_security(
    position: SourcePosition,
    *,
    report: pd.Timestamp,
    instruments: pd.DataFrame,
    snapshot: pd.DataFrame,
    price_column: str,
    minimum_amount: float,
) -> None:
    symbol = position.symbol.upper()
    if symbol not in instruments.index:
        raise WeeklyBasketPreflightError(f"{symbol} is not listed in instruments")
    instrument = instruments.loc[symbol]
    list_date = _date_series(pd.Series([instrument.get("list_date")])).iloc[0]
    delist_date = _date_series(pd.Series([instrument.get("delist_date")])).iloc[0]
    normally_listed = (
        not pd.isna(list_date)
        and list_date <= report
        and (pd.isna(delist_date) or delist_date > report)
        and str(instrument.get("list_status", "")).upper() == "L"
    )
    if not normally_listed:
        raise WeeklyBasketPreflightError(f"{symbol} is not normally listed")
    if symbol not in snapshot.index:
        raise WeeklyBasketPreflightError(f"{symbol} is missing a prior-session price")
    row = snapshot.loc[symbol]
    name = str(instrument.get("name", position.name)).upper()
    if bool(row["is_st"]) or "ST" in name:
        raise WeeklyBasketPreflightError(f"{symbol} is ST")
    if bool(row["is_suspended"]):
        raise WeeklyBasketPreflightError(f"{symbol} is suspended")
    price = pd.to_numeric(pd.Series([row[price_column]]), errors="coerce").iloc[0]
    if pd.isna(price) or price <= 0:
        raise WeeklyBasketPreflightError(f"{symbol} has an invalid price")
    amount = pd.to_numeric(pd.Series([row["amount"]]), errors="coerce").iloc[0]
    if pd.isna(amount) or amount < minimum_amount:
        raise WeeklyBasketPreflightError(f"{symbol} amount is below minimum")


def run_weekly_basket_preflight(
    positions: Sequence[SourcePosition],
    *,
    report_date: str,
    instruments_path: Path,
    market_path: Path,
    calendar_path: Path,
    minimum_amount: float = 20_000_000,
    enforce_stable_paths: bool = True,
) -> WeeklyBasketPreflight:
    """Validate timing, listing, status, price and liquidity before delivery."""
    paths = {
        "instruments": Path(instruments_path),
        "market": Path(market_path),
        "calendar": Path(calendar_path),
    }
    if enforce_stable_paths:
        for path in paths.values():
            _stable(path)
        for position in positions:
            _stable(Path(position.artifact_path))
    report = pd.to_datetime(report_date, format="%Y%m%d", errors="coerce")
    if pd.isna(report):
        raise WeeklyBasketPreflightError("report_date must use YYYYMMDD")
    report_week, prior = _calendar_context(paths["calendar"], report)

    if len(positions) != 10 or len({row.symbol.upper() for row in positions}) != 10:
        raise WeeklyBasketPreflightError("basket must contain 10 unique positions")
    if any(not row.symbol.upper().endswith((".SH", ".SZ")) for row in positions):
        raise WeeklyBasketPreflightError("basket contains a non-SSE/SZSE symbol")

    instruments = pd.read_parquet(paths["instruments"])
    instrument_symbol = _symbol_column(instruments)
    instruments = instruments.copy()
    instruments[instrument_symbol] = instruments[instrument_symbol].astype(str).str.upper()
    instruments = instruments.set_index(instrument_symbol)
    snapshot, price_column = _market_snapshot(paths["market"], prior)
    for position in positions:
        _validate_security(
            position,
            report=report,
            instruments=instruments,
            snapshot=snapshot,
            price_column=price_column,
            minimum_amount=minimum_amount,
        )
    return WeeklyBasketPreflight(
        report_date=report.strftime("%Y%m%d"),
        report_week=report_week,
        prior_session=prior.strftime("%Y%m%d"),
        position_count=len(positions),
        input_hashes={name: _hash(path) for name, path in paths.items()},
    )


__all__ = [
    "WeeklyBasketPreflight",
    "WeeklyBasketPreflightError",
    "run_weekly_basket_preflight",
]
