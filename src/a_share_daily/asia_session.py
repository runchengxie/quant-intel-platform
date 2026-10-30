"""Independent Asian sessions and dated holiday evening observations."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import exchange_calendars as xcals
import pandas as pd

MARKETS = {
    "HK": ("XHKG", "^HSI", "香港"),
    "JP": ("XTKS", "^N225", "日本"),
    "KR": ("XKRX", "^KS11", "韩国"),
}


def _day(value: str) -> pd.Timestamp:
    text = value.replace("-", "")
    if len(text) != 8 or not text.isdigit():
        raise ValueError("date must be YYYYMMDD or YYYY-MM-DD")
    return cast(pd.Timestamp, pd.Timestamp(datetime.strptime(text, "%Y%m%d")))


def session_rows(calendar_path: Path, start: str, end: str) -> list[dict]:
    first, last = _day(start), _day(end)
    if first > last:
        raise ValueError("calendar range reversed")
    frame = pd.read_parquet(calendar_path)
    if not {"exchange", "cal_date", "is_open"} <= set(frame.columns):
        raise ValueError("owner calendar schema incomplete")
    frame = frame.loc[frame.exchange == "SSE"].copy()
    frame["day"] = frame.cal_date.astype(str).map(_day)
    if frame.day.duplicated().any() or not frame.is_open.isin([0, 1]).all():
        raise ValueError("owner calendar ambiguous")
    flags = dict(zip(frame.day, frame.is_open, strict=True))
    calendars = {
        key: xcals.get_calendar(
            spec[0],
            start=(first.to_pydatetime() - timedelta(days=20)).date(),
            end=(last.to_pydatetime() + timedelta(days=20)).date(),
        )
        for key, spec in MARKETS.items()
    }
    rows = []
    for day in pd.date_range(first, last):
        if day not in flags:
            raise ValueError("owner calendar coverage incomplete")
        markets = {"CN": bool(flags[day])}
        for key, calendar in calendars.items():
            if day < calendar.first_session or day > calendar.last_session:
                raise ValueError("exchange calendar coverage incomplete")
            markets[key] = bool(calendar.is_session(day))
        rows.append(
            {
                "cal_date": day.strftime("%Y%m%d"),
                "is_open": int(any(markets.values())),
                "markets": markets,
            }
        )
    return rows


def session_status(calendar_path: Path, date: str) -> dict[str, bool]:
    return session_rows(calendar_path, date, date)[0]["markets"]


class QuoteUnavailable(ValueError):
    """Safe diagnostic metadata without provider exception text."""

    def __init__(self, code: str, observed: str = "unknown", expected: str = "unknown"):
        super().__init__(code)
        self.code = code
        self.observed = observed
        self.expected = expected


def _diagnostic_date(value: object) -> str:
    try:
        return _day(str(value)).strftime("%Y-%m-%d")
    except ValueError:
        return "unknown"


def _quote_error(quote: dict, code: str, day: pd.Timestamp) -> QuoteUnavailable:
    return QuoteUnavailable(
        code,
        _diagnostic_date(quote.get("observed_date", quote.get("date", "unknown"))),
        _diagnostic_date(quote.get("expected_date", day.strftime("%Y-%m-%d"))),
    )


def _fetch_quotes(day: pd.Timestamp, markets: dict[str, bool]) -> dict:
    import yfinance as yf

    quotes = {}
    for key, (calendar_name, symbol, _) in MARKETS.items():
        if not markets[key]:
            continue
        # A daily bar fetched before close can still be intraday even if
        # other requests finish after close. Never issue that request early.
        started = datetime.now(UTC)
        if started < xcals.get_calendar(calendar_name).session_close(day):
            quotes[key] = {"error": "not_closed_at_request", "reason_code": "not_closed_at_request"}
            continue
        try:
            frame = yf.Ticker(symbol).history(
                start=(day.to_pydatetime() - timedelta(days=15)).strftime("%Y-%m-%d"),
                end=(day.to_pydatetime() + timedelta(days=1)).strftime("%Y-%m-%d"),
                auto_adjust=False,
            )
            # Daily-bar timestamps label local session opens, not publication times.
            dates = _validated_bar_dates(frame, calendar_name, day)
            quotes[key] = {
                "date": dates[-1].strftime("%Y%m%d"),
                "previous_date": dates[-2].strftime("%Y%m%d"),
                "close": float(frame.Close.iloc[-1]),
                "previous_close": float(frame.Close.iloc[-2]),
                "retrieved_at": datetime.now(UTC).isoformat(),
            }
        except Exception as exc:  # noqa: BLE001 - isolate each independent source
            code = exc.code if isinstance(exc, QuoteUnavailable) else "source_request_failed"
            quotes[key] = {"error": code, "reason_code": code}
            if isinstance(exc, QuoteUnavailable):
                quotes[key].update(observed_date=exc.observed, expected_date=exc.expected)
    return quotes


def _validated_bar_dates(frame: pd.DataFrame, calendar_name: str, day: pd.Timestamp) -> list:
    calendar = xcals.get_calendar(calendar_name)
    if len(frame) < 2 or not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise QuoteUnavailable("incomplete_bars_or_timezone", expected=day.strftime("%Y-%m-%d"))
    dates = [_day(value.tz_convert(calendar.tz).strftime("%Y%m%d")) for value in frame.index]
    if dates[-1] != day:
        raise QuoteUnavailable(
            "stale_session", dates[-1].strftime("%Y-%m-%d"), day.strftime("%Y-%m-%d")
        )
    if dates[-2] != calendar.previous_session(day) or len(set(dates)) != len(dates):
        raise QuoteUnavailable(
            "preceding_session_missing_or_duplicate",
            dates[-2].strftime("%Y-%m-%d"),
            calendar.previous_session(day).strftime("%Y-%m-%d"),
        )
    return dates


def _valid_price(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value > 0
    )


def _observation(key: str, day: pd.Timestamp, quote: dict) -> dict:
    if _day(str(quote["date"])) != day:
        raise ValueError("quote date differs from session")
    if not all(_valid_price(quote[field]) for field in ("close", "previous_close")):
        raise ValueError("quote prices invalid")
    close, previous = float(quote["close"]), float(quote["previous_close"])
    if not all(math.isfinite(value) and value > 0 for value in (close, previous)):
        raise ValueError("quote prices invalid")
    change_pct = (close / previous - 1) * 100
    if not math.isfinite(change_pct):
        raise ValueError("quote return invalid")
    calendar_name, symbol, _ = MARKETS[key]
    calendar = xcals.get_calendar(calendar_name)
    source_time = calendar.session_close(day).isoformat()
    source_url = f"https://finance.yahoo.com/quote/{symbol}/history/"
    evidence = hashlib.sha256(
        json.dumps(
            [key, day.isoformat(), close, previous, source_time], separators=(",", ":")
        ).encode()
    ).hexdigest()
    return {
        "status": "open",
        "observation_date": day.strftime("%Y-%m-%d"),
        "source_time_kind": "exchange_session_close",
        "close": close,
        "change_pct": change_pct,
        "source_url": source_url,
        "source_time": source_time,
        "evidence_id": f"asia.close.{evidence}",
    }


INDEX_NAMES = {"HK": "恒生指数", "JP": "日经225", "KR": "KOSPI"}


def _validate_quote_session(
    quote: dict, calendar_name: str, day: pd.Timestamp, current: datetime
) -> None:
    if "error" in quote:
        raise _quote_error(quote, str(quote.get("reason_code", "source_request_failed")), day)
    if _day(str(quote.get("date", ""))) != day:
        raise _quote_error(quote, "stale_session", day)
    previous_date = str(quote.get("previous_date", ""))
    calendar = xcals.get_calendar(calendar_name)
    if _day(previous_date) != calendar.previous_session(day):
        raise _quote_error(quote, "preceding_session_missing", day)
    retrieved = datetime.fromisoformat(quote.get("retrieved_at", ""))
    if retrieved.tzinfo is None or retrieved < calendar.session_close(day) or retrieved > current:
        raise _quote_error(quote, "retrieval_before_close_or_invalid", day)


def _missing_diagnostic(row: dict, symbol: str, issue: QuoteUnavailable) -> str:
    row.update(reason_code=issue.code, observed_date=issue.observed, expected_date=issue.expected)
    return f"{symbol}: {issue.code}; observed={issue.observed}; expected={issue.expected}"


def build_asia_report(
    calendar_path: Path, date: str, *, quotes: dict | None = None, now: datetime | None = None
) -> dict:
    """Build the same independently dated facts for ordinary and CN-holiday reports."""
    day = _day(date)
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        raise ValueError("observation clock must include timezone")
    markets = session_status(calendar_path, date)
    supplied = _fetch_quotes(day, markets) if quotes is None else quotes
    current = now or datetime.now(UTC)
    observations: dict[str, Any] = {
        "CN": {"status": "open" if markets["CN"] else "closed", "observation_date": None}
    }
    errors = []
    for key, (calendar_name, symbol, _) in MARKETS.items():
        row: dict[str, Any] = {"status": "closed", "observation_date": None}
        if markets[key]:
            close_time = xcals.get_calendar(calendar_name).session_close(day)
            row["status"] = "pending" if current < close_time else "missing"
            if row["status"] == "missing":
                quote = supplied.get(key, {})
                try:
                    _validate_quote_session(quote, calendar_name, day, current)
                    row = _observation(key, day, quote)
                    row["previous_session"] = _day(quote["previous_date"]).strftime("%Y-%m-%d")
                    row["previous_close"] = quote["previous_close"]
                    row["retrieved_at"] = quote["retrieved_at"]
                except QuoteUnavailable as exc:
                    errors.append(_missing_diagnostic(row, symbol, exc))
                except (ValueError, KeyError, TypeError):
                    errors.append(
                        _missing_diagnostic(
                            row, symbol, _quote_error(quote, "incomplete_quote", day)
                        )
                    )
        observations[key] = row
    return {
        "schema_version": "market_intel.asia_evening.v2",
        "date": day.strftime("%Y%m%d"),
        "generated_at": current.isoformat(),
        "markets": observations,
        "errors": errors,
    }


def validate_asia_report(payload: dict, date: str, markets: dict[str, bool]) -> None:
    if (
        payload.get("schema_version") != "market_intel.asia_evening.v2"
        or payload.get("date") != _day(date).strftime("%Y%m%d")
        or set(payload.get("markets", {})) != set(markets)
    ):
        raise ValueError("Asia report identity or coverage invalid")
    generated = datetime.fromisoformat(payload["generated_at"])
    if generated.tzinfo is None or generated > datetime.now(UTC):
        raise ValueError("Asia report timestamp invalid")
    for key in MARKETS:
        row = payload["markets"][key]
        status = row.get("status")
        if status == "open" and markets[key]:
            _validate_observation(row, date, key)
            _validate_previous_observation(row, date, key)
            retrieved = datetime.fromisoformat(row["retrieved_at"])
            if (
                retrieved.tzinfo is None
                or retrieved < datetime.fromisoformat(row["source_time"])
                or retrieved > generated
            ):
                raise ValueError("observation retrieval before close or invalid")
            if datetime.fromisoformat(row["source_time"]) > generated:
                raise ValueError("observation precedes actual close")
        elif status in (("missing", "pending") if markets[key] else ("closed",)):
            if row.get("observation_date") is not None or any(
                field in row for field in ("close", "change_pct")
            ):
                raise ValueError("unavailable market contains stale quotes")
            if status == "pending" and generated >= xcals.get_calendar(
                MARKETS[key][0]
            ).session_close(_day(date)):
                raise ValueError("pending market already closed")
        else:
            raise ValueError("market status invalid")


def _validate_previous_observation(row: dict, date: str, key: str) -> None:
    previous = xcals.get_calendar(MARKETS[key][0]).previous_session(_day(date))
    if row.get("previous_session") != previous.strftime("%Y-%m-%d") or not _valid_price(
        row.get("previous_close")
    ):
        raise ValueError("preceding observation invalid")
    expected = (row["close"] / row["previous_close"] - 1) * 100
    if not math.isfinite(expected) or not math.isclose(row["change_pct"], expected):
        raise ValueError("observation return differs from preceding close")


def expire_pending_observations(payload: dict, *, now: datetime | None = None) -> None:
    """An earlier pending receipt cannot describe an already closed market as pending."""
    current = now or datetime.now(UTC)
    for key, (calendar_name, symbol, _) in MARKETS.items():
        row = payload["markets"][key]
        if row["status"] == "pending" and current >= xcals.get_calendar(
            calendar_name
        ).session_close(_day(payload["date"])):
            row["status"] = "missing"
            diagnostic = _missing_diagnostic(
                row,
                symbol,
                QuoteUnavailable(
                    "expired_pending", expected=_day(payload["date"]).strftime("%Y-%m-%d")
                ),
            )
            payload.setdefault("errors", []).append(diagnostic)


def render_asia_overview(payload: dict) -> str:
    """Six-column public module; unavailable markets never borrow stale values."""
    lines = [
        "### 亚洲市场概览",
        "",
        "| 市场 | 指数 | 数据日期 | 收盘 | 涨跌幅 | 状态 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for key, (_, _, label) in MARKETS.items():
        row = payload["markets"][key]
        if row["status"] == "open":
            _validate_observation(row, payload["date"], key)
            lines.append(
                f"| {label} | {INDEX_NAMES[key]} | {row['observation_date']} | "
                f"{row['close']:.2f} | {row['change_pct']:+.2f}% | 已收盘 |"
            )
        else:
            status = {"closed": "休市", "missing": "当日数据缺失", "pending": "未收盘"}[
                row["status"]
            ]
            lines.append(f"| {label} | {INDEX_NAMES[key]} | — | — | — | {status} |")
    metadata = {
        "date": _day(payload["date"]).strftime("%Y-%m-%d"),
        "source_time_kind": "exchange_session_close",
    }
    encoded = json.dumps(metadata, sort_keys=True, separators=(",", ":"))
    lines.extend(["", f"<!-- market_intel.asia_overview.v1 {encoded} -->", ""])
    for key, (_, _, label) in MARKETS.items():
        row = payload["markets"][key]
        if row["status"] == "open":
            lines.append(
                f"- [{label}收盘数据]({row['source_url']})；{row['source_time']}；"
                f"证据：`{row['evidence_id']}`"
            )
    lines.extend(["", "来源时间为交易所日历规定的实际收盘时间；日线时间戳仅标识当地交易日。"])
    if payload.get("errors"):
        lines.append("数据警告：" + "；".join(payload["errors"]))
    return "\n".join(lines) + "\n"


def build_holiday_report(calendar_path: Path, date: str, *, quotes: dict | None = None) -> dict:
    day = _day(date)
    markets = session_status(calendar_path, date)
    if markets["CN"]:
        raise ValueError("holiday report requires closed A-share market")
    supplied = _fetch_quotes(day, markets) if quotes is None else quotes
    observations: dict[str, Any] = {}
    for key, opened in markets.items():
        observations[key] = {"status": "missing" if opened else "closed", "observation_date": None}
        if opened and key in supplied:
            with suppress(ValueError, KeyError, TypeError):
                observations[key] = _observation(key, day, supplied[key])
    payload = {
        "schema_version": "market_intel.asia_evening.v1",
        "date": day.strftime("%Y%m%d"),
        "generated_at": datetime.now(UTC).isoformat(),
        "markets": observations,
    }
    validate_holiday_report(payload, date, markets)
    return payload


def validate_holiday_report(payload: dict, date: str, markets: dict[str, bool]) -> None:
    if set(markets) != {"CN", "HK", "JP", "KR"} or any(
        type(value) is not bool for value in markets.values()
    ):
        raise ValueError("invalid session flags")
    if (
        markets["CN"]
        or payload.get("schema_version") != "market_intel.asia_evening.v1"
        or payload.get("date") != _day(date).strftime("%Y%m%d")
    ):
        raise ValueError("holiday report identity invalid")
    generated = datetime.fromisoformat(payload["generated_at"])
    if generated.tzinfo is None or generated > datetime.now(UTC):
        raise ValueError("holiday report timestamp invalid")
    observed = 0
    if set(payload["markets"]) != set(markets):
        raise ValueError("market coverage incomplete")
    for key, opened in markets.items():
        row = payload["markets"][key]
        status = row.get("status")
        if not opened:
            if (
                status != "closed"
                or row.get("observation_date") is not None
                or any(field in row for field in ("close", "change_pct"))
            ):
                raise ValueError("closed market contains current quotes")
        elif status == "missing":
            if row.get("observation_date") is not None or any(
                field in row for field in ("close", "change_pct")
            ):
                raise ValueError("missing market contains stale quotes")
        elif status == "open":
            _validate_observation(row, date, key)
            observed += 1
        else:
            raise ValueError("market status invalid")
    if not observed:
        raise ValueError("no current open-market observations")


def _validate_observation(row: dict, date: str, key: str) -> None:
    if row.get("observation_date") != _day(date).strftime("%Y-%m-%d"):
        raise ValueError("observation session stale")
    if (
        not _valid_price(row["close"])
        or not isinstance(row["change_pct"], (int, float))
        or isinstance(row["change_pct"], bool)
        or not math.isfinite(row["change_pct"])
    ):
        raise ValueError("observation prices invalid")
    if row.get("source_time_kind", "exchange_session_close") != "exchange_session_close":
        raise ValueError("observation time kind invalid")
    source_time = datetime.fromisoformat(row["source_time"])
    expected_close = xcals.get_calendar(MARKETS[key][0]).session_close(_day(date))
    if (
        source_time.tzinfo is None
        or source_time > datetime.now(UTC)
        or source_time != expected_close
    ):
        raise ValueError("observation time invalid")
    if not str(row["source_url"]).startswith("https://") or not str(row["evidence_id"]).startswith(
        "asia.close."
    ):
        raise ValueError("observation provenance invalid")


def render_holiday_report(payload: dict) -> str:
    return f"# 亚洲市场收盘复盘（{payload['date']}）\n\nA 股今日休市。\n\n" + render_asia_overview(
        payload
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calendar", type=Path, required=True)
    parser.add_argument("--date")
    parser.add_argument("--rows", action="store_true")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--report-output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.rows:
            print(json.dumps(session_rows(args.calendar, args.start, args.end)))
            return 0
        markets = session_status(args.calendar, args.date)
        if not any(markets.values()):
            print(json.dumps(markets))
            return 20
        if args.report_output:
            payload = build_asia_report(args.calendar, args.date)
            args.report_output.mkdir(parents=True, exist_ok=True)
            for suffix, content in (
                ("json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n"),
                (
                    "md",
                    render_holiday_report(payload)
                    if not markets["CN"]
                    else f"# 亚洲市场收盘复盘（{payload['date']}）\n\n"
                    + render_asia_overview(payload),
                ),
            ):
                target = args.report_output / f"{payload['date']}.{suffix}"
                staging = target.with_suffix(f".{suffix}.tmp")
                staging.write_text(content, encoding="utf-8")
                staging.replace(target)
        print(json.dumps(markets))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"Asia session unavailable: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
