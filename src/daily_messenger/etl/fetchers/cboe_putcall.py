"""Fetch Cboe daily put/call ratios."""

from __future__ import annotations

import contextlib
import csv
import datetime as dt
import io
import logging
import re
from dataclasses import dataclass
from zoneinfo import ZoneInfo

import requests

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 15
EXCHANGE_TZ = ZoneInfo("America/Chicago")

CSV_SOURCES: dict[str, str] = {
    "equity": "https://cdn.cboe.com/resources/options/volume_and_call_put_ratios/equitypc.csv",
    "index": "https://cdn.cboe.com/resources/options/volume_and_call_put_ratios/indexpc.csv",
    "spx_spxw": "https://cdn.cboe.com/resources/options/volume_and_call_put_ratios/spxpc.csv",
    "vix": "https://cdn.cboe.com/resources/options/volume_and_call_put_ratios/vixpc.csv",
}

DAILY_MARKET_STATS_URL = "https://www.cboe.com/markets/us/options/market-statistics/daily/"
LEGACY_MARKET_SUMMARY_URL = "https://www.cboe.com/us/options/market_statistics/"
CSV_MAX_AGE_DAYS = 14
TOTAL_PATTERN = re.compile(
    r"Total[^<]*P/C\s*RATIO[^0-9]*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE | re.DOTALL
)
DAILY_RATIO_LABELS = {
    "TOTAL PUT/CALL RATIO": "total",
    "INDEX PUT/CALL RATIO": "index",
    "EXCHANGE TRADED PRODUCTS PUT/CALL RATIO": "etp",
    "EQUITY PUT/CALL RATIO": "equity",
    "CBOE VOLATILITY INDEX (VIX) PUT/CALL RATIO": "vix",
    "SPX + SPXW PUT/CALL RATIO": "spx_spxw",
}


@dataclass
class FetchStatus:
    name: str
    ok: bool
    message: str = ""


def _init_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    with contextlib.suppress(Exception):
        session.get("https://www.cboe.com", timeout=REQUEST_TIMEOUT)
    return session


def _parse_ratio(value: str) -> float | None:
    text = value.strip().replace("%", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _latest_csv_row(content: str) -> tuple[str, float]:
    reader = csv.reader(io.StringIO(content))
    latest_date: dt.date | None = None
    latest_ratio: float | None = None
    for row in reader:
        if not row:
            continue
        header = row[0].strip().upper()
        if header == "DATE":
            # reset accumulation for the data section
            latest_date = None
            latest_ratio = None
            continue
        if not row[0].strip():
            continue
        try:
            parsed_date = dt.datetime.strptime(row[0].strip(), "%m/%d/%Y").date()
        except ValueError:
            continue
        ratio = _parse_ratio(row[-1])
        if ratio is None:
            continue
        if latest_date is None or parsed_date > latest_date:
            latest_date = parsed_date
            latest_ratio = ratio
    if latest_date is None or latest_ratio is None:
        raise RuntimeError("CSV 缺少有效的日期或比值")
    return latest_date.isoformat(), latest_ratio


def _fetch_csv_ratios(
    session: requests.Session,
) -> tuple[dict[str, float], str | None, list[str]]:
    ratios: dict[str, float] = {}
    dates: list[str] = []
    errors: list[str] = []
    for key, url in CSV_SOURCES.items():
        try:
            resp = session.get(url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            date_str, ratio = _latest_csv_row(resp.text)
            ratios[key] = ratio
            dates.append(date_str)
        except Exception as exc:  # noqa: BLE001
            logger.warning("_fetch_csv_ratios" + " 捕获到异常", exc_info=True)
            errors.append(f"{key}: {exc}")
    unique_dates = sorted(set(dates), reverse=True)
    return ratios, (unique_dates[0] if unique_dates else None), errors


def _fetch_total_today(session: requests.Session) -> float | None:
    try:
        resp = session.get(LEGACY_MARKET_SUMMARY_URL, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except Exception:  # noqa: BLE001
        logger.warning("_fetch_total_today" + " 捕获到异常", exc_info=True)
        return None
    match = TOTAL_PATTERN.search(resp.text)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _fetch_daily_page_ratios(session: requests.Session) -> tuple[dict[str, float], str | None]:
    try:
        resp = session.get(DAILY_MARKET_STATS_URL, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logger.warning("_fetch_daily_page_ratios" + " 捕获到异常", exc_info=True)
        return {}, str(exc)
    text = resp.text.replace('\\"', '"')
    ratios: dict[str, float] = {}
    for match in re.finditer(
        r'"name"\s*:\s*"([^"]+PUT/CALL RATIO)"\s*,\s*"value"\s*:\s*"([0-9]+(?:\.[0-9]+)?)"',
        text,
        re.IGNORECASE,
    ):
        label = match.group(1).upper()
        key = DAILY_RATIO_LABELS.get(label)
        if not key:
            continue
        try:
            ratios[key] = float(match.group(2))
        except ValueError:
            continue
    if ratios:
        return ratios, None
    return {}, "Cboe Daily Market Statistics 页面缺少 Put/Call ratios"


def _csv_is_stale(date_str: str | None) -> bool:
    if not date_str:
        return True
    try:
        parsed = dt.datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return True
    today = dt.datetime.now(tz=EXCHANGE_TZ).date()
    return (today - parsed).days > CSV_MAX_AGE_DAYS


def fetch() -> tuple[dict[str, dict[str, object]], FetchStatus]:
    """Fetch put/call ratios from the published CSV archives."""

    session = _init_session()
    ratios, page_error = _fetch_daily_page_ratios(session)
    date_str: str | None = None
    errors: list[str] = []

    if not ratios:
        ratios, date_str, errors = _fetch_csv_ratios(session)
        if ratios and _csv_is_stale(date_str):
            errors.append(f"CSV 数据过旧: {date_str}")
            ratios = {}
        if ratios:
            message = "Cboe Put/Call CSV 数据已更新"
        else:
            total_ratio = _fetch_total_today(session)
            if total_ratio is not None:
                ratios["total"] = total_ratio
                message = "Cboe 总体 Put/Call 使用当日页面兜底"
            else:
                if page_error:
                    errors.insert(0, f"daily_page: {page_error}")
                detail = "; ".join(errors) if errors else "未能获取 Cboe 数据"
                return {}, FetchStatus(name="cboe_put_call", ok=False, message=detail)
    else:
        message = "Cboe Daily Market Statistics 数据已更新"

    now_ct = dt.datetime.now(tz=EXCHANGE_TZ)
    payload: dict[str, dict[str, object]] = {
        "put_call": {
            "as_of_exchange_tz": EXCHANGE_TZ.key,
            "as_of_utc": now_ct.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z"),
            "source": "cboe_daily_market_statistics"
            if not date_str
            else "cboe_volume_put_call_csv",
        }
    }
    if date_str:
        payload["put_call"]["as_of_date"] = date_str
    payload["put_call"].update(ratios)

    if errors and ratios:
        message = f"{message}（部分字段缺失: {'; '.join(errors)}）"

    return payload, FetchStatus(name="cboe_put_call", ok=True, message=message)
