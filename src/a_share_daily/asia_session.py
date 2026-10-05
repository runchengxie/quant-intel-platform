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


def _fetch_quotes(day: pd.Timestamp, markets: dict[str, bool]) -> dict:
    import yfinance as yf

    quotes = {}
    for key, (_, symbol, _) in MARKETS.items():
        if not markets[key]:
            continue
        try:
            frame = yf.Ticker(symbol).history(
                start=(day.to_pydatetime() - timedelta(days=15)).strftime("%Y-%m-%d"),
                end=(day.to_pydatetime() + timedelta(days=1)).strftime("%Y-%m-%d"),
                auto_adjust=False,
            )
            if len(frame) >= 2:
                quotes[key] = {
                    "date": frame.index[-1].strftime("%Y%m%d"),
                    "close": float(frame.Close.iloc[-1]),
                    "previous_close": float(frame.Close.iloc[-2]),
                }
        except Exception:  # noqa: BLE001, S112 - preserve observations from other markets
            continue
    return quotes


def _observation(key: str, day: pd.Timestamp, quote: dict) -> dict:
    if _day(str(quote["date"])) != day:
        raise ValueError("quote date differs from session")
    close, previous = float(quote["close"]), float(quote["previous_close"])
    if not all(math.isfinite(value) and value > 0 for value in (close, previous)):
        raise ValueError("quote prices invalid")
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
        "close": close,
        "change_pct": (close / previous - 1) * 100,
        "source_url": source_url,
        "source_time": source_time,
        "evidence_id": f"asia.close.{evidence}",
    }


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
        not math.isfinite(float(row["close"]))
        or float(row["close"]) <= 0
        or not math.isfinite(float(row["change_pct"]))
    ):
        raise ValueError("observation prices invalid")
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
    lines = [
        f"# 亚洲市场收盘复盘（{payload['date']}）",
        "",
        "A 股今日休市。",
        "",
        "| 市场 | 状态 | 收盘 | 涨跌幅 |",
        "| --- | --- | --- | --- |",
    ]
    for key, row in payload["markets"].items():
        label = "A 股" if key == "CN" else MARKETS[key][2]
        if row["status"] == "open":
            lines.append(
                f"| {label} | {row['observation_date']} | {row['close']:.2f} "
                f"| {row['change_pct']:+.2f}% |"
            )
        else:
            lines.append(
                f"| {label} | {'休市' if row['status'] == 'closed' else '当日数据缺失'} | — | — |"
            )
    lines.extend(["", "## 数据来源", ""])
    for key, row in payload["markets"].items():
        if row["status"] == "open":
            lines.append(
                f"- [{MARKETS[key][2]}收盘数据]({row['source_url']})；{row['source_time']}；"
                f"证据：`{row['evidence_id']}`"
            )
    return "\n".join(lines) + "\n"


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
            payload = build_holiday_report(args.calendar, args.date)
            args.report_output.mkdir(parents=True, exist_ok=True)
            for suffix, content in (
                ("json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n"),
                ("md", render_holiday_report(payload)),
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
