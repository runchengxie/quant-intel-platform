"""Financial Modeling Prep theme metrics helpers."""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from daily_messenger.etl.config import coerce_api_key as _coerce_api_key
from daily_messenger.etl.http import request_json as _request_json
from daily_messenger.etl.types import FetchStatus

logger = logging.getLogger(__name__)

THROTTLE_DISABLED = os.getenv("DM_DISABLE_THROTTLE", "").lower() in {"1", "true", "yes"}

FMP_THEME_SYMBOLS = {
    "ai": ["NVDA", "MSFT", "GOOGL", "AMD"],
    "magnificent7": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"],
}
FMP_BASE_URL = "https://financialmodelingprep.com/stable"

QuotePayloads = dict[str, dict[str, Any]]
FundamentalPayloads = dict[str, dict[str, float | None]]
EdgarFundamentalsResult = tuple[FundamentalPayloads, list[str], list[str]]


@dataclass(frozen=True)
class ThemeMetricDependencies:
    """Runtime integrations needed by the FMP theme aggregation helper."""

    fetch_yahoo_quotes: Callable[[list[str]], QuotePayloads]
    fetch_price_only_quotes: Callable[[list[str], dict[str, Any] | None], QuotePayloads]
    fetch_edgar_fundamentals: Callable[[Iterable[str]], EdgarFundamentalsResult]
    yahoo_allowed: Callable[[], bool]


@dataclass(frozen=True)
class _QuoteFetchResult:
    quotes: dict[str, dict[str, Any]]
    source: str
    errors: list[str]


@dataclass(frozen=True)
class _FundamentalFetchResult:
    fundamentals: dict[str, dict[str, float | None]]
    missing_cik: list[str]
    edgar_errors: list[str]
    edgar_available: bool
    fmp_fallback_used: bool
    fmp_fallback_errors: list[str]


@dataclass(frozen=True)
class _SymbolMetric:
    row: dict[str, Any]
    change: float | None
    pe: float | None
    ps: float | None
    pb: float | None
    market_cap: float | None


def _sleep(seconds: float) -> None:
    if seconds <= 0 or THROTTLE_DISABLED:
        return
    time.sleep(seconds)


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_payload_entries(payload: Any) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        for key in ("metrics", "ttmMetrics", "data", "metric", "items"):
            block = payload.get(key)
            if isinstance(block, list):
                entries.extend(item for item in block if isinstance(item, dict))
            elif isinstance(block, dict):
                entries.append(block)
        if not entries and payload:
            entries.append(payload)
    elif isinstance(payload, list):
        entries = [item for item in payload if isinstance(item, dict)]
    return entries


def _entry_date_key(entry: dict[str, Any]) -> str:
    """Pick the first available date-like key from an FMP record."""
    for key in ("date", "period", "fiscalDateEnding"):
        value = entry.get(key)
        if value:
            return str(value)
    return ""


def _pick_metric(
    record: Mapping[str, Any],
    lower_map: Mapping[str, Any],
    keys: Iterable[str],
) -> float | None:
    """Return the first parseable float among the candidate keys (any case)."""
    for key in keys:
        value = record.get(key, lower_map.get(key.lower()))
        if value is not None:
            number = _safe_float(value)
            if number is not None:
                return number
    return None


def _derive_from_market_cap(
    metric: float | None,
    market_cap: float | None,
    ratio: float | None,
) -> float | None:
    """Derive a missing metric from market cap and its ratio (ps/pb/pe TTM)."""
    if metric is None and market_cap not in (None, 0.0) and ratio not in (None, 0.0):
        return float(market_cap) / float(ratio)
    return metric


_FMP_METRIC_KEYS: dict[str, list[str]] = {
    "market_cap": ["marketCap", "market_cap"],
    "pe_ttm": ["priceToEarningsRatioTTM", "peRatioTTM", "peTTM"],
    "ps_ttm": ["priceToSalesRatioTTM", "priceToSalesRatio", "psTTM"],
    "pb_ttm": ["priceToBookRatioTTM", "priceToBookRatio", "pbTTM"],
    "revenue_ttm": ["revenueTTM", "RevenueTTM", "revenue_ttm"],
    "net_income_ttm": ["netIncomeTTM", "NetIncomeTTM", "net_income_ttm"],
    "shares_diluted_latest": [
        "weightedAverageSharesDilutedTTM",
        "weightedAverageShsOutDilTTM",
        "weightedAverageShsOutDil",
        "WeightedAverageSharesDilutedTTM",
        "WeightedAverageShsOutDilTTM",
    ],
    "equity_latest": [
        "shareholdersEquityTTM",
        "ShareholdersEquityTTM",
        "totalShareholdersEquityTTM",
        "TotalShareholdersEquityTTM",
        "shareholdersequityttm",
    ],
}


def _extract_fmp_metrics(
    payload: Any,
    ratios_payload: Any | None = None,
) -> dict[str, float | None]:
    entries = _extract_payload_entries(payload)
    entries.extend(_extract_payload_entries(ratios_payload))
    if not entries:
        return {}

    entries.sort(key=_entry_date_key, reverse=True)
    record: dict[str, Any] = {}
    for entry in entries:
        record.update(entry)
    lower_map = {str(k).lower(): v for k, v in record.items()}

    market_cap = _pick_metric(record, lower_map, _FMP_METRIC_KEYS["market_cap"])
    pe_ttm = _pick_metric(record, lower_map, _FMP_METRIC_KEYS["pe_ttm"])
    ps_ttm = _pick_metric(record, lower_map, _FMP_METRIC_KEYS["ps_ttm"])
    pb_ttm = _pick_metric(record, lower_map, _FMP_METRIC_KEYS["pb_ttm"])
    revenue = _pick_metric(record, lower_map, _FMP_METRIC_KEYS["revenue_ttm"])
    net_income = _pick_metric(record, lower_map, _FMP_METRIC_KEYS["net_income_ttm"])
    shares = _pick_metric(record, lower_map, _FMP_METRIC_KEYS["shares_diluted_latest"])
    equity = _pick_metric(record, lower_map, _FMP_METRIC_KEYS["equity_latest"])

    revenue = _derive_from_market_cap(revenue, market_cap, ps_ttm)
    net_income = _derive_from_market_cap(net_income, market_cap, pe_ttm)
    equity = _derive_from_market_cap(equity, market_cap, pb_ttm)

    if not any(
        val is not None
        for val in (revenue, net_income, shares, equity, market_cap, pe_ttm, ps_ttm, pb_ttm)
    ):
        return {}
    return {
        "revenue_ttm": revenue,
        "net_income_ttm": net_income,
        "shares_diluted_latest": shares,
        "equity_latest": equity,
        "market_cap": market_cap,
        "pe_ttm": pe_ttm,
        "ps_ttm": ps_ttm,
        "pb_ttm": pb_ttm,
    }


def _fetch_fmp_fundamentals(
    symbols: Iterable[str],
    api_key: str,
) -> tuple[dict[str, dict[str, float | None]], list[str]]:
    results: dict[str, dict[str, float | None]] = {}
    errors: list[str] = []
    for ticker in sorted({s.upper() for s in symbols if s}):
        params = {"symbol": ticker, "apikey": api_key}
        metrics_payload: Any | None = None
        ratios_payload: Any | None = None
        request_errors: list[str] = []
        try:
            metrics_payload = _request_json(f"{FMP_BASE_URL}/key-metrics-ttm", params=params)
        except Exception as exc:  # noqa: BLE001
            logger.warning("_fetch_fmp_fundamentals" + " 捕获到异常", exc_info=True)
            request_errors.append(f"key-metrics-ttm: {exc}")
        try:
            ratios_payload = _request_json(f"{FMP_BASE_URL}/ratios-ttm", params=params)
        except Exception as exc:  # noqa: BLE001
            logger.warning("_fetch_fmp_fundamentals" + " 捕获到异常", exc_info=True)
            request_errors.append(f"ratios-ttm: {exc}")
        if metrics_payload is None and ratios_payload is None:
            errors.append(f"{ticker}: {'; '.join(request_errors)}")
            continue
        metrics = _extract_fmp_metrics(metrics_payload, ratios_payload)
        if metrics:
            results[ticker] = metrics
        else:
            errors.append(f"{ticker}: FMP 数据不足")
        _sleep(0.2)
    return results, errors


def _mean(values: list[float | None]) -> float | None:
    filtered = [v for v in values if v is not None]
    if not filtered:
        return None
    return sum(filtered) / len(filtered)


def _all_theme_symbols(theme_symbols: dict[str, list[str]]) -> list[str]:
    all_symbols: list[str] = []
    for symbols in theme_symbols.values():
        all_symbols.extend(symbols)
    return all_symbols


def _quote_failure_status(errors: list[str], fallback_note: str | None = None) -> FetchStatus:
    detail = "; ".join(errors) if errors else "未知原因"
    if fallback_note:
        detail = f"{detail}；{fallback_note}"
    return FetchStatus(name="fmp_theme", ok=False, message=f"主题估值获取失败: {detail}")


def _fetch_quotes_price_first(
    all_symbols: list[str],
    api_keys: dict[str, Any],
    dependencies: ThemeMetricDependencies,
    *,
    allow_yahoo: bool,
) -> tuple[_QuoteFetchResult | None, FetchStatus | None]:
    errors: list[str] = []
    try:
        quotes = dependencies.fetch_price_only_quotes(all_symbols, api_keys)
        return _QuoteFetchResult(quotes=quotes, source="price_only", errors=errors), None
    except Exception as exc:  # noqa: BLE001
        logger.warning("_fetch_quotes_price_first" + " 捕获到异常", exc_info=True)
        errors.append(f"price_only: {exc}")

    if not allow_yahoo:
        note = "已禁用 Yahoo 兜底" if errors else "无可用行情来源"
        return None, _quote_failure_status(errors, note)

    try:
        quotes = dependencies.fetch_yahoo_quotes(all_symbols)
    except Exception as fallback_exc:  # noqa: BLE001
        logger.warning("_fetch_quotes_price_first" + " 捕获到异常", exc_info=True)
        errors.append(f"Yahoo: {fallback_exc}")
        return None, _quote_failure_status(errors)
    return _QuoteFetchResult(quotes=quotes, source="yahoo", errors=errors), None


def _fetch_quotes_yahoo_first(
    all_symbols: list[str],
    api_keys: dict[str, Any],
    dependencies: ThemeMetricDependencies,
) -> tuple[_QuoteFetchResult | None, FetchStatus | None]:
    errors: list[str] = []
    try:
        quotes = dependencies.fetch_yahoo_quotes(all_symbols)
        return _QuoteFetchResult(quotes=quotes, source="yahoo", errors=errors), None
    except Exception as exc:  # noqa: BLE001
        logger.warning("_fetch_quotes_yahoo_first" + " 捕获到异常", exc_info=True)
        errors.append(f"Yahoo: {exc}")

    try:
        quotes = dependencies.fetch_price_only_quotes(all_symbols, api_keys)
    except Exception as fallback_exc:  # noqa: BLE001
        logger.warning("_fetch_quotes_yahoo_first" + " 捕获到异常", exc_info=True)
        errors.append(f"price_only: {fallback_exc}")
        return None, _quote_failure_status(errors)
    return _QuoteFetchResult(quotes=quotes, source="price_only", errors=errors), None


def _fetch_theme_quotes(
    all_symbols: list[str],
    api_keys: dict[str, Any],
    dependencies: ThemeMetricDependencies,
) -> tuple[_QuoteFetchResult | None, FetchStatus | None]:
    allow_yahoo = dependencies.yahoo_allowed()
    prefer_stooq = os.getenv("PREFER_STOOQ", "0") == "1" or not allow_yahoo
    if prefer_stooq:
        return _fetch_quotes_price_first(
            all_symbols,
            api_keys,
            dependencies,
            allow_yahoo=allow_yahoo,
        )
    return _fetch_quotes_yahoo_first(all_symbols, api_keys, dependencies)


_REQUIRED_FUNDAMENTAL_FIELDS = (
    "net_income_ttm",
    "revenue_ttm",
    "shares_diluted_latest",
    "equity_latest",
)


def _symbols_needing_fmp_fallback(
    all_symbols: list[str],
    fundamentals: dict[str, dict[str, float | None]],
) -> list[str]:
    needs_fmp: list[str] = []
    for symbol in {sym.upper() for sym in all_symbols}:
        metrics = fundamentals.get(symbol)
        if not metrics or any(
            metrics.get(field) in (None, 0.0) for field in _REQUIRED_FUNDAMENTAL_FIELDS
        ):
            needs_fmp.append(symbol)
    return needs_fmp


def _merge_fmp_fundamentals(
    fundamentals: dict[str, dict[str, float | None]],
    fmp_data: dict[str, dict[str, float | None]],
) -> None:
    for symbol, metrics in fmp_data.items():
        merged = fundamentals.setdefault(symbol, {})
        for key, value in metrics.items():
            if value is None:
                continue
            existing = merged.get(key)
            if existing in (None, 0.0):
                merged[key] = value


def _fetch_theme_fundamentals(
    all_symbols: list[str],
    api_keys: dict[str, Any],
    dependencies: ThemeMetricDependencies,
) -> _FundamentalFetchResult:
    fundamentals: dict[str, dict[str, float | None]] = {}
    missing_cik: list[str] = []
    edgar_errors: list[str] = []
    try:
        fundamentals, missing_cik, edgar_errors = dependencies.fetch_edgar_fundamentals(all_symbols)
    except Exception as exc:  # noqa: BLE001
        logger.warning("_fetch_theme_fundamentals" + " 捕获到异常", exc_info=True)
        edgar_errors.append(str(exc))

    edgar_available = bool(fundamentals)
    fmp_fallback_used = False
    fmp_fallback_errors: list[str] = []
    fmp_key = _coerce_api_key(api_keys.get("financial_modeling_prep"))
    if fmp_key:
        needs_fmp = _symbols_needing_fmp_fallback(all_symbols, fundamentals)
        if needs_fmp:
            fmp_data, fallback_errors = _fetch_fmp_fundamentals(needs_fmp, fmp_key)
            if fmp_data:
                fmp_fallback_used = True
                _merge_fmp_fundamentals(fundamentals, fmp_data)
            fmp_fallback_errors.extend(fallback_errors)

    return _FundamentalFetchResult(
        fundamentals=fundamentals,
        missing_cik=missing_cik,
        edgar_errors=edgar_errors,
        edgar_available=edgar_available,
        fmp_fallback_used=fmp_fallback_used,
        fmp_fallback_errors=fmp_fallback_errors,
    )


def _quote_ps_ratio(quote: dict[str, Any]) -> float | None:
    ratio = quote.get("priceToSalesRatioTTM")
    if ratio is None:
        ratio = quote.get("priceToSalesRatio")
    return _safe_float(ratio)


def _resolve_market_cap(
    quote: dict[str, Any],
    price: float | None,
    metrics: dict[str, float | None] | None,
) -> float | None:
    market_cap = _safe_float(quote.get("marketCap"))
    if market_cap not in (None, 0.0) or not metrics:
        return market_cap

    market_cap = _safe_float(metrics.get("market_cap"))
    if market_cap not in (None, 0.0):
        quote["marketCap"] = market_cap
        return market_cap

    shares = _safe_float(metrics.get("shares_diluted_latest"))
    if price is not None and shares not in (None, 0.0):
        market_cap = float(price) * float(shares)
        quote["marketCap"] = market_cap
    return market_cap


def _compute_fundamental_ratios(
    price: float | None,
    market_cap: float | None,
    metrics: dict[str, float | None] | None,
) -> tuple[float | None, float | None, float | None]:
    if not metrics:
        return None, None, None

    net_income = metrics.get("net_income_ttm")
    shares = metrics.get("shares_diluted_latest")
    revenue = metrics.get("revenue_ttm")
    equity = metrics.get("equity_latest")

    computed_pe: float | None = None
    if price is not None and net_income is not None and shares not in (None, 0.0):
        eps = net_income / shares if shares else None
        if eps not in (None, 0.0):
            computed_pe = price / eps
    if computed_pe is None and market_cap not in (None, 0.0) and net_income not in (None, 0.0):
        computed_pe = float(market_cap) / float(net_income)

    computed_ps = (
        float(market_cap) / float(revenue)
        if market_cap not in (None, 0.0) and revenue not in (None, 0.0)
        else None
    )
    computed_pb = (
        float(market_cap) / float(equity)
        if market_cap not in (None, 0.0) and equity not in (None, 0.0)
        else None
    )
    return (
        computed_pe if computed_pe is not None else _safe_float(metrics.get("pe_ttm")),
        computed_ps if computed_ps is not None else _safe_float(metrics.get("ps_ttm")),
        computed_pb if computed_pb is not None else _safe_float(metrics.get("pb_ttm")),
    )


def _round_metric(value: float | None) -> float | None:
    return round(value, 2) if isinstance(value, (int, float)) else None


def _build_symbol_metric(
    symbol: str,
    quote: dict[str, Any],
    source: str,
    metrics: dict[str, float | None] | None,
) -> _SymbolMetric:
    quote_source = quote.get("source") or source or "unknown"
    change = _safe_float(quote.get("changesPercentage"))
    price = _safe_float(quote.get("price"))
    market_cap = _resolve_market_cap(quote, price, metrics)
    computed_pe, computed_ps, computed_pb = _compute_fundamental_ratios(price, market_cap, metrics)
    pe_value = computed_pe if computed_pe is not None else _safe_float(quote.get("pe"))
    ps_value = computed_ps if computed_ps is not None else _quote_ps_ratio(quote)

    return _SymbolMetric(
        row={
            "symbol": symbol,
            "price": _round_metric(price),
            "change_pct": _round_metric(change),
            "pe": _round_metric(pe_value),
            "ps": _round_metric(ps_value),
            "pb": _round_metric(computed_pb),
            "market_cap": _round_metric(market_cap),
            "source": quote_source,
        },
        change=change,
        pe=pe_value,
        ps=ps_value,
        pb=computed_pb,
        market_cap=market_cap,
    )


def _build_theme_payload(
    symbols: list[str],
    quotes_norm: dict[str, dict[str, Any]],
    source: str,
    fundamentals: dict[str, dict[str, float | None]],
) -> dict[str, Any] | None:
    change_values: list[float | None] = []
    pe_values: list[float | None] = []
    ps_values: list[float | None] = []
    pb_values: list[float | None] = []
    market_cap_total = 0.0
    symbol_rows: list[dict[str, Any]] = []

    for symbol in symbols:
        quote = quotes_norm.get(symbol.upper())
        if not quote:
            continue
        metric = _build_symbol_metric(symbol, quote, source, fundamentals.get(symbol.upper()))
        change_values.append(metric.change)
        pe_values.append(metric.pe)
        ps_values.append(metric.ps)
        if metric.pb is not None:
            pb_values.append(metric.pb)
        if metric.market_cap not in (None, 0.0):
            market_cap_total += float(metric.market_cap)
        symbol_rows.append(metric.row)

    if not change_values and not pe_values and not ps_values and not pb_values:
        return None

    change_avg = _mean(change_values)
    pe_avg = _mean(pe_values)
    ps_avg = _mean(ps_values)
    pb_avg = _mean(pb_values)
    return {
        "change_pct": round(change_avg, 2) if change_avg is not None else None,
        "avg_pe": round(pe_avg, 2) if pe_avg is not None else None,
        "avg_ps": round(ps_avg, 2) if ps_avg is not None else None,
        "avg_pb": round(pb_avg, 2) if pb_avg is not None else None,
        "market_cap": round(market_cap_total, 2) if market_cap_total else None,
        "symbols": symbol_rows,
    }


def _build_theme_payloads(
    theme_symbols: dict[str, list[str]],
    quote_result: _QuoteFetchResult,
    fundamental_result: _FundamentalFetchResult,
) -> dict[str, Any]:
    quotes_norm = {symbol.upper(): payload for symbol, payload in quote_result.quotes.items()}
    themes: dict[str, Any] = {}
    for theme, symbols in theme_symbols.items():
        payload = _build_theme_payload(
            symbols,
            quotes_norm,
            quote_result.source,
            fundamental_result.fundamentals,
        )
        if payload is not None:
            themes[theme] = payload
    return themes


def _fundamentals_label(result: _FundamentalFetchResult) -> str:
    if not result.fundamentals:
        return ""
    if result.edgar_available and result.fmp_fallback_used:
        return "EDGAR + FMP 财报"
    if result.edgar_available:
        return "EDGAR 财报"
    if result.fmp_fallback_used:
        return "FMP 财报"
    return "财报数据"


def _fundamental_issue_items(result: _FundamentalFetchResult) -> list[str]:
    issue_items: list[str] = []
    if result.missing_cik:
        issue_items.append(f"缺少CIK: {', '.join(sorted(result.missing_cik))}")
    issue_items.extend(result.edgar_errors)
    issue_items.extend(result.fmp_fallback_errors)
    return issue_items


def _short_issue_detail(issue_items: list[str]) -> str:
    if not issue_items:
        return ""
    if len(issue_items) > 2:
        return "; ".join(issue_items[:2]) + f" 等 {len(issue_items)} 项"
    return "; ".join(issue_items)


def _price_only_status_message(
    quote_result: _QuoteFetchResult,
    fundamental_result: _FundamentalFetchResult,
) -> str:
    fallback_providers = sorted(
        {
            str(payload.get("source") or "price_only").split(":", 1)[0]
            for payload in quote_result.quotes.values()
        }
    )
    fallback_label = " + ".join(fallback_providers) if fallback_providers else "价格兜底"
    fundamentals_label = _fundamentals_label(fundamental_result)
    if fundamental_result.fundamentals and fundamentals_label:
        message = f"主题估值使用 {fallback_label} 报价兜底 + {fundamentals_label}"
    elif fundamental_result.fundamentals:
        message = f"主题估值使用 {fallback_label} 报价兜底 + 财报数据"
    else:
        message = f"主题估值使用 {fallback_label} 报价兜底，仅含行情字段"

    detail_parts: list[str] = []
    if quote_result.errors:
        detail_parts.append("; ".join(quote_result.errors))
    issue_detail = _short_issue_detail(_fundamental_issue_items(fundamental_result))
    if issue_detail:
        detail_parts.append(issue_detail)
    if detail_parts:
        message = f"{message}（{'；'.join(part for part in detail_parts if part)}）"
    return message


def _yahoo_status(
    fundamental_result: _FundamentalFetchResult,
) -> FetchStatus:
    fundamentals_label = _fundamentals_label(fundamental_result)
    detail = _short_issue_detail(_fundamental_issue_items(fundamental_result))
    if fundamental_result.fundamentals and fundamentals_label:
        message = f"主题估值使用 Yahoo 行情 + {fundamentals_label}"
        if detail:
            message = f"{message}（{detail}）"
        return FetchStatus(name="fmp_theme", ok=True, message=message)
    if fundamental_result.fundamentals:
        message = "主题估值使用 Yahoo 行情 + 财报数据"
        if detail:
            message = f"{message}（{detail}）"
        return FetchStatus(name="fmp_theme", ok=True, message=message)

    message = "主题估值缺少 EDGAR 财报，仅使用行情"
    if detail:
        message = f"{message}（{detail}）"
    return FetchStatus(name="fmp_theme", ok=False, message=message)


def _theme_metrics_status(
    quote_result: _QuoteFetchResult,
    fundamental_result: _FundamentalFetchResult,
) -> FetchStatus:
    if quote_result.source == "price_only":
        return FetchStatus(
            name="fmp_theme",
            ok=True,
            message=_price_only_status_message(quote_result, fundamental_result),
        )
    return _yahoo_status(fundamental_result)


def _fetch_theme_metrics_from_fmp(
    api_keys: dict[str, Any],
    dependencies: ThemeMetricDependencies,
    theme_symbols: dict[str, list[str]] | None = None,
) -> tuple[dict[str, Any], FetchStatus]:
    theme_symbols = theme_symbols or FMP_THEME_SYMBOLS
    all_symbols = _all_theme_symbols(theme_symbols)
    quote_result, failure_status = _fetch_theme_quotes(all_symbols, api_keys, dependencies)
    if quote_result is None:
        return {}, failure_status or FetchStatus(
            name="fmp_theme",
            ok=False,
            message="主题估值获取失败: 未知原因",
        )

    fundamental_result = _fetch_theme_fundamentals(all_symbols, api_keys, dependencies)
    themes = _build_theme_payloads(theme_symbols, quote_result, fundamental_result)
    if not themes:
        return {}, FetchStatus(name="fmp_theme", ok=False, message="主题估值数据为空")
    return themes, _theme_metrics_status(quote_result, fundamental_result)
