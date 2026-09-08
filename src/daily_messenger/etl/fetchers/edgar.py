"""SEC EDGAR fundamentals fetcher helpers."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable
from datetime import datetime
from typing import Any

import requests

from daily_messenger.etl.http import RETRY_EDGAR
from daily_messenger.etl.http import request_json as _request_json
from daily_messenger.etl.types import FetchStatus

logger = logging.getLogger(__name__)


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


EDGAR_TICKER_URL = "https://www.sec.gov/files/company_tickers.json"
EDGAR_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
EDGAR_ALLOWED_FORMS = {
    "10-Q",
    "10-Q/A",
    "10-K",
    "10-K/A",
    "20-F",
    "40-F",
    "6-K",
    "6-K/A",
}
DEFAULT_EDGAR_USER_AGENT = "DailyMessenger/0.1 (contact: [email protected])"


def _resolve_edgar_user_agent() -> str:
    value = os.getenv("EDGAR_USER_AGENT")
    if value is None:
        return DEFAULT_EDGAR_USER_AGENT
    trimmed = value.strip()
    if not trimmed:
        raise RuntimeError(
            "EDGAR_USER_AGENT is empty; set a value like 'DailyMessenger/1.0 (contact: you@example.com)'"
        )
    return trimmed


EDGAR_USER_AGENT = _resolve_edgar_user_agent()
EDGAR_THROTTLE = 0.25


def _init_edgar_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": EDGAR_USER_AGENT,
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",
        }
    )
    return session


def _edgar_request_json(session: requests.Session, url: str) -> Any:
    try:
        payload = _request_json(
            url,
            session=session,
            headers={
                "User-Agent": EDGAR_USER_AGENT,
                "Accept": "application/json",
                "Accept-Encoding": "gzip, deflate",
            },
            policy=RETRY_EDGAR,
            after_each_sleep=EDGAR_THROTTLE,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("_edgar_request_json" + " 捕获到异常", exc_info=True)
        raise RuntimeError(f"EDGAR 请求失败: {exc}") from exc
    if not isinstance(payload, (dict, list)):
        raise RuntimeError("EDGAR 响应解析失败")
    return payload


_EDGAR_TICKER_CACHE: dict[str, str] | None = None


def _load_edgar_ticker_mapping(session: requests.Session) -> dict[str, str]:
    global _EDGAR_TICKER_CACHE
    if _EDGAR_TICKER_CACHE is not None:
        return _EDGAR_TICKER_CACHE
    payload = _edgar_request_json(session, EDGAR_TICKER_URL)
    mapping: dict[str, str] = {}
    if isinstance(payload, dict):
        values = payload.values()
    elif isinstance(payload, list):
        values = payload
    else:
        values = []
    for item in values:
        if not isinstance(item, dict):
            continue
        ticker = str(item.get("ticker") or "").upper()
        cik_raw = item.get("cik_str")
        if cik_raw is None:
            continue
        try:
            cik = f"{int(cik_raw):010d}"
        except (TypeError, ValueError):
            continue
        if ticker:
            mapping[ticker] = cik
    if not mapping:
        raise RuntimeError("EDGAR 代码映射为空")
    _EDGAR_TICKER_CACHE = mapping
    return mapping


def _fetch_edgar_companyfacts(session: requests.Session, cik: str) -> dict[str, Any]:
    url = EDGAR_COMPANYFACTS_URL.format(cik=cik)
    payload = _edgar_request_json(session, url)
    facts = payload.get("facts")
    if not isinstance(facts, dict):
        raise RuntimeError("EDGAR 返回缺少 facts 字段")
    return facts


def _edgar_select_fact(
    facts: dict[str, Any], candidates: Iterable[tuple[str, Iterable[str]]]
) -> dict[str, Any] | None:
    for taxonomy, names in candidates:
        bucket = facts.get(taxonomy)
        if not isinstance(bucket, dict):
            continue
        for name in names:
            fact = bucket.get(name)
            if isinstance(fact, dict):
                return fact
    return None


def _edgar_collect_entries(
    fact: dict[str, Any] | None, unit_candidates: Iterable[str]
) -> list[dict[str, Any]]:
    if not fact:
        return []
    units = fact.get("units")
    if not isinstance(units, dict):
        return []
    entries: list[dict[str, Any]] = []
    for unit in unit_candidates:
        data = units.get(unit)
        if isinstance(data, list):
            entries.extend([item for item in data if isinstance(item, dict)])
    if not entries and units:
        first_key = next(iter(units))
        data = units.get(first_key)
        if isinstance(data, list):
            entries.extend([item for item in data if isinstance(item, dict)])
    return entries


def _edgar_parse_date(value: str | None) -> str | None:
    if not value:
        return None
    return str(value)


def _edgar_classify_period(entry: dict[str, Any], end: str) -> str:
    fp = str(entry.get("fp") or "").upper()
    if fp.startswith("Q"):
        return "Q"
    start = entry.get("start")
    if isinstance(start, str):
        try:
            start_dt = datetime.fromisoformat(start)
            end_dt = datetime.fromisoformat(end)
        except ValueError:
            return "A"
        duration = (end_dt - start_dt).days
        return "Q" if 70 <= duration <= 100 else "A"
    return "A"


def _edgar_ttm_from_fact(fact: dict[str, Any] | None) -> float | None:
    entries = _edgar_collect_entries(fact, ("USD",))
    quarterly: list[tuple[str, float]] = []
    annual: list[tuple[str, float]] = []
    for entry in entries:
        end = _edgar_parse_date(entry.get("end"))
        val = _safe_float(entry.get("val"))
        form = str(entry.get("form") or "").upper()
        if end is None or val is None or form not in EDGAR_ALLOWED_FORMS:
            continue
        if _edgar_classify_period(entry, end) == "Q":
            quarterly.append((end, val))
        else:
            annual.append((end, val))
    quarterly.sort(key=lambda item: item[0], reverse=True)
    if len(quarterly) >= 4:
        return sum(val for _, val in quarterly[:4])
    if annual:
        annual.sort(key=lambda item: item[0], reverse=True)
        return annual[0][1]
    if quarterly:
        return sum(val for _, val in quarterly)
    return None


def _edgar_latest_quarter_value(fact: dict[str, Any] | None) -> float | None:
    entries = _edgar_collect_entries(fact, ("shares", "pure"))
    quarterly: list[tuple[str, float]] = []
    for entry in entries:
        end = _edgar_parse_date(entry.get("end"))
        val = _safe_float(entry.get("val"))
        form = str(entry.get("form") or "").upper()
        fp = str(entry.get("fp") or "").upper()
        if end is None or val is None or form not in EDGAR_ALLOWED_FORMS:
            continue
        if fp.startswith("Q"):
            quarterly.append((end, val))
    quarterly.sort(key=lambda item: item[0], reverse=True)
    if quarterly:
        return quarterly[0][1]
    fallback = [
        (entry.get("end"), _safe_float(entry.get("val")))
        for entry in entries
        if _safe_float(entry.get("val")) is not None and entry.get("end")
    ]
    fallback.sort(key=lambda item: str(item[0]), reverse=True)
    return fallback[0][1] if fallback else None


def _edgar_latest_instant(fact: dict[str, Any] | None) -> float | None:
    entries = _edgar_collect_entries(fact, ("USD",))
    instants: list[tuple[str, float]] = []
    for entry in entries:
        end = _edgar_parse_date(entry.get("end"))
        val = _safe_float(entry.get("val"))
        form = str(entry.get("form") or "").upper()
        if end is None or val is None or form not in EDGAR_ALLOWED_FORMS:
            continue
        instants.append((end, val))
    instants.sort(key=lambda item: item[0], reverse=True)
    return instants[0][1] if instants else None


def _extract_edgar_metrics(facts: dict[str, Any]) -> dict[str, float | None]:
    revenue_fact = _edgar_select_fact(
        facts,
        [
            (
                "us-gaap",
                [
                    "Revenues",
                    "SalesRevenueNet",
                    "RevenueFromContractWithCustomerExcludingAssessedTax",
                ],
            ),
            ("ifrs-full", ["Revenue", "RevenueFromContractsWithCustomers"]),
        ],
    )
    net_income_fact = _edgar_select_fact(
        facts,
        [
            ("us-gaap", ["NetIncomeLoss", "ProfitLoss"]),
            ("ifrs-full", ["ProfitLoss", "ProfitLossAttributableToOwnersOfParent"]),
        ],
    )
    shares_fact = _edgar_select_fact(
        facts,
        [
            (
                "us-gaap",
                [
                    "WeightedAverageNumberOfDilutedSharesOutstanding",
                    "DilutedEPSWeightedAverageSharesOutstanding",
                    "WeightedAverageNumberOfSharesOutstandingDiluted",
                    "WeightedAverageNumberOfSharesOutstanding",
                ],
            ),
            (
                "ifrs-full",
                [
                    "WeightedAverageDilutedSharesOutstanding",
                    "WeightedAverageShares",
                    "WeightedAverageNumberOfOrdinarySharesOutstanding",
                    "WeightedAverageNumberOfOrdinarySharesOutstandingDiluted",
                ],
            ),
        ],
    )
    equity_fact = _edgar_select_fact(
        facts,
        [
            (
                "us-gaap",
                [
                    "StockholdersEquity",
                    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
                    "TotalEquity",
                    "Equity",
                ],
            ),
            (
                "ifrs-full",
                [
                    "Equity",
                    "EquityIncludingNoncontrollingInterests",
                    "EquityAttributableToOwnersOfParent",
                ],
            ),
        ],
    )

    revenue_ttm = _edgar_ttm_from_fact(revenue_fact)
    net_income_ttm = _edgar_ttm_from_fact(net_income_fact)
    shares_latest = _edgar_latest_quarter_value(shares_fact)
    equity_latest = _edgar_latest_instant(equity_fact)

    if not any(
        value is not None for value in (revenue_ttm, net_income_ttm, shares_latest, equity_latest)
    ):
        return {}

    return {
        "revenue_ttm": revenue_ttm,
        "net_income_ttm": net_income_ttm,
        "shares_diluted_latest": shares_latest,
        "equity_latest": equity_latest,
    }


def _fetch_edgar_fundamentals(
    symbols: Iterable[str],
) -> tuple[dict[str, dict[str, float | None]], list[str], list[str]]:
    session = _init_edgar_session()
    mapping = _load_edgar_ticker_mapping(session)
    results: dict[str, dict[str, float | None]] = {}
    missing: list[str] = []
    errors: list[str] = []
    for ticker in sorted({s.upper() for s in symbols if s}):
        cik = mapping.get(ticker)
        if not cik:
            missing.append(ticker)
            continue
        try:
            facts = _fetch_edgar_companyfacts(session, cik)
        except Exception as exc:  # noqa: BLE001
            logger.warning("_fetch_edgar_fundamentals" + " 捕获到异常", exc_info=True)
            errors.append(f"{ticker}: {exc}")
            continue
        metrics = _extract_edgar_metrics(facts)
        if metrics:
            results[ticker] = metrics
        else:
            errors.append(f"{ticker}: 财报数据不足")
    return results, missing, errors


def _edgar_healthcheck() -> FetchStatus:
    session = _init_edgar_session()
    try:
        mapping = _load_edgar_ticker_mapping(session)
        if not mapping:
            raise RuntimeError("EDGAR 代码映射为空")
        cik = mapping.get("AAPL")
        if not cik:
            try:
                cik = next(iter(mapping.values()))
            except StopIteration as exc:
                raise RuntimeError("EDGAR 代码映射缺失 CIK") from exc
        _fetch_edgar_companyfacts(session, cik)
        return FetchStatus(name="edgar", ok=True, message=f"EDGAR 正常（UA={EDGAR_USER_AGENT}）")
    except Exception as exc:  # noqa: BLE001
        logger.warning("_edgar_healthcheck" + " 捕获到异常", exc_info=True)
        return FetchStatus(name="edgar", ok=False, message=f"{exc}")
    finally:
        session.close()
