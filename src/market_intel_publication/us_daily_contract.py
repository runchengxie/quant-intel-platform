"""Import a validated platform daily report into the public Pages tree."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .us_news_contract import REVISION_FIELDS, validate_news_payload

SCHEMA_PREFIX = "1."
DATE_FIELDS = {"as_of", "generated_at", "source_time", "retrieved_at"}
REQUIRED_FIELDS = {
    "schema_version",
    "as_of",
    "generated_at",
    "run_id",
    "facts",
    "claims",
    "source_status",
}
FACT_LABELS = {
    "index.spx.change_percent": ("标普 500 日涨跌", "%"),
    "index.dow.change_percent": ("道指日涨跌", "%"),
    "index.nasdaq.change_percent": ("纳指日涨跌", "%"),
    "index.russell2000.change_percent": ("罗素 2000 日涨跌", "%"),
    "treasury.2y.change_bp": ("2 年期美债收益率日变动", "bp"),
    "treasury.5y.change_bp": ("5 年期美债收益率日变动", "bp"),
    "treasury.10y.change_bp": ("10 年期美债收益率日变动", "bp"),
    "treasury.30y.change_bp": ("30 年期美债收益率日变动", "bp"),
    "treasury.2y.level_percent": ("2 年期美债收益率水平", "%"),
    "treasury.5y.level_percent": ("5 年期美债收益率水平", "%"),
    "treasury.10y.level_percent": ("10 年期美债收益率水平", "%"),
    "treasury.30y.level_percent": ("30 年期美债收益率水平", "%"),
    "cross_asset.brent.close": ("布伦特期货收盘", "美元/桶"),
    "cross_asset.brent.change_percent": ("布伦特日涨跌", "%"),
    "cross_asset.gold.close": ("COMEX 黄金期货收盘", "美元/金衡盎司"),
    "cross_asset.gold.change_percent": ("黄金日涨跌", "%"),
    "cross_asset.silver.close": ("COMEX 白银期货收盘", "美元/金衡盎司"),
    "cross_asset.silver.change_percent": ("白银日涨跌", "%"),
    "cross_asset.bitcoin.close": ("CME 比特币期货收盘", "美元/BTC"),
    "cross_asset.bitcoin.change_percent": ("比特币期货日涨跌", "%"),
    "cross_asset.bitcoin_spot.close": ("BTC/USD 现货收盘", "美元/BTC"),
    "cross_asset.bitcoin_spot.change_percent": ("BTC/USD 现货日涨跌", "%"),
    "macro.cpi_yoy": ("CPI 同比", "%"),
    "macro.pce_yoy": ("PCE 同比", "%"),
    "macro.unemployment_rate": ("失业率", "%"),
    "macro.payroll_change_thousands": ("非农就业月变动", "千人"),
}
FRED_URL = r"https://fred\.stlouisfed\.org/series/[A-Z0-9]+"
TREASURY_URL = r"https://home\.treasury\.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates\.csv/all/\d{6}\?_format=csv&field_tdr_date_value_month=\d{6}&page=&type=daily_treasury_yield_curve"
YAHOO_URLS = {
    "brent": None,
    "gold": None,
    "silver": None,
    "bitcoin": r"https://finance\.yahoo\.com/quote/BTC%3DF/history/",
}
FUTURES_MONTH_CODES = "FGHJKMNQUVXZ"
DATED_DELIVERY_MONTHS = {"gold": (2, 4, 6, 8, 12), "silver": (3, 5, 7, 9, 12)}
LEGACY_COMMODITY_SYMBOLS = {"brent": "BZ%3DF", "gold": "GC%3DF", "silver": "SI%3DF"}


def _dated_futures_symbol(asset: str, report_date: date) -> str | None:
    if asset == "brent":
        offset, root, exchange = 2, "BZ", "NYM"
    elif asset in DATED_DELIVERY_MONTHS:
        offset = next(
            step
            for step in range(1, 13)
            if (report_date.month - 1 + step) % 12 + 1 in DATED_DELIVERY_MONTHS[asset]
        )
        root, exchange = {"gold": "GC", "silver": "SI"}[asset], "CMX"
    else:
        return None
    absolute_month = report_date.month - 1 + offset
    month = absolute_month % 12 + 1
    year = report_date.year + absolute_month // 12
    return f"{root}{FUTURES_MONTH_CODES[month - 1]}{year % 100:02d}.{exchange}"


FMP_CRYPTO_URL = "https://site.financialmodelingprep.com/developer/docs/stable/cryptocurrency-historical-price-eod-full"
BTC_SPOT_SOURCES = {
    ("Financial Modeling Prep", FMP_CRYPTO_URL): "BTC/USD cryptocurrency EOD (FMP BTCUSD)",
    (
        "Data provided by CoinGecko",
        "https://www.coingecko.com/en/api",
    ): "BTC/USD spot at 16:00 ET (CoinGecko bitcoin/USD)",
    (
        "Kraken",
        "https://www.kraken.com/prices/bitcoin",
    ): "BTC/USD spot at 16:00 ET (Kraken XBT/USD)",
}
YAHOO_INDEX_URLS = {
    "spx": r"https://finance\.yahoo\.com/quote/%5EGSPC/history/",
    "dow": r"https://finance\.yahoo\.com/quote/%5EDJI/history/",
    "nasdaq": r"https://finance\.yahoo\.com/quote/%5EIXIC/history/",
    "russell2000": r"https://finance\.yahoo\.com/quote/%5ERUT/history/",
}
EQUITY_ID = re.compile(r"equity\.([a-z]{1,5})\.(close|change_percent)")
ALPACA_STOCK_BARS_URL = "https://docs.alpaca.markets/us/reference/stockbars"
CORE_EQUITIES = {"MSFT", "AAPL", "NVDA", "AMZN", "GOOGL", "META"}
MISSING_LABELS = {
    "quotes": "指数行情",
    "research": "研究解释",
    "fred": "部分 FRED 数据",
    "rates_lag": "美债收益率当日变动",
    "cross_asset": "部分跨资产行情",
    "equities": "部分美股个股行情",
    "btc_spot": "比特币现货行情",
}
ASSET_GAP_LABELS = {
    "brent": "布伦特期货行情",
    "gold": "黄金期货行情",
    "silver": "白银期货行情",
    "bitcoin_spot": "比特币现货行情",
}
SOURCE_STATUS_LABELS = {
    "rates": "美债收益率",
    "macro": "宏观数据",
    "quotes": "指数行情",
    "research": "研究材料",
    "cross_asset": "跨资产行情",
    "btc_spot": "比特币现货",
    "equities": "美股个股行情",
}
SOURCE_QUALITY_LABELS = {"ok": "已核实", "reviewed": "已审阅", "degraded": "有缺项"}
SOURCE_REASON_LABELS = {
    "all_indices_fresh": "目标交易日数据齐全",
    "all_contracts_fresh": "目标交易日合约数据齐全",
    "source_audited": "来源已逐条核查",
    "not_connected": "研究材料尚未接入，不提供未经核实的解释",
    "ok": "来源状态正常",
    "all_equities_fresh": "核心观察股票行情齐全",
    "one_or_more_equities_unavailable": "部分股票行情暂缺",
}
PUBLIC_FACT_FIELDS = (
    "id",
    "metric",
    "instrument",
    "value",
    "previous",
    "change",
    "unit",
    "source",
    "source_url",
    "source_time",
    "retrieved_at",
    "quality",
    "observation_date",
)
PUBLIC_EVENT_FIELDS = ("id", "event_type", "actual", "source_url", "quality")
PUBLIC_CLAIM_FIELDS = (
    "claim",
    "evidence_ids",
    "sources",
    "confidence",
    "status",
    "provider",
)
PUBLIC_SECTION_FIELDS = ("key", "title", "facts", "claims")
RESEARCH_SECTION_TITLES = {
    "market": "美股市场表现",
    "cross_asset": "跨资产行情",
    "drivers": "市场驱动因素",
    "macro": "经济数据与美联储动态",
    "company_news": "公司新闻",
    "movers": "主要上涨与下跌个股",
}


def _valid_report_time(payload: dict[str, Any]) -> bool:
    market_time = datetime.fromisoformat(payload["as_of"]).astimezone(ZoneInfo("America/New_York"))
    report_date = date.fromisoformat(str(payload["run_id"]).removeprefix("daily-"))
    age = (market_time.date() - report_date).days
    if payload.get("quality_summary", {}).get("revision") == "historical_backfill":
        return 0 < age <= 10
    return market_time.date() == report_date or (
        market_time.date() == report_date + timedelta(days=1) and market_time.time() < time(9, 30)
    )


def _valid_claims(claims: list[dict[str, Any]]) -> bool:
    return all(
        claim.get("evidence_ids")
        and claim.get("sources")
        and all(str(url).startswith("https://") for url in claim["sources"])
        for claim in claims
    )


def _normalize(value: Any, key: str = "") -> Any:
    if isinstance(value, dict):
        return {name: _normalize(item, name) for name, item in value.items()}
    if isinstance(value, list):
        return [_normalize(item, key) for item in value]
    if isinstance(value, str) and key in DATE_FIELDS:
        return datetime.fromisoformat(value)
    return value


def _valid_content_hash(payload: dict[str, Any]) -> bool:
    content = dict(payload)
    claimed = content.get("content_hash")
    content["content_hash"] = None
    digest = hashlib.sha256(
        json.dumps(_normalize(content), default=str, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    return claimed == digest


def _unique_evidence_ids(payload: dict[str, Any]) -> bool:
    return all(
        len(identifiers) == len(set(identifiers))
        for identifiers in (
            [row.get("id") for row in payload["facts"]],
            [row.get("id") for row in payload.get("events", [])],
        )
    )


def _valid_market_fact(  # noqa: PLR0911 - preserve audited validation branches
    fact: dict[str, Any], report_date: str, *, allow_legacy_commodity: bool = False
) -> bool:
    fact_id = str(fact.get("id") or "")
    observed = fact.get("observation_date")
    source_url = str(fact.get("source_url") or "")
    unit = fact.get("unit")
    equity_match = EQUITY_ID.fullmatch(fact_id)
    if equity_match:
        symbol, field = equity_match.groups()
        yahoo_url = f"https://finance.yahoo.com/quote/{symbol.upper()}/history/"
        source_valid = (fact.get("source") == "Yahoo Finance" and source_url == yahoo_url) or (
            fact.get("source") == "Alpaca SIP" and source_url == ALPACA_STOCK_BARS_URL
        )
        return (
            fact.get("instrument") == symbol.upper()
            and source_valid
            and fact.get("quality") == "ok"
            and observed == report_date
            and fact.get("metric") == ("stock_close" if field == "close" else "daily_return")
            and unit == ("USD/share" if field == "close" else "percent")
            and isinstance(fact.get("value"), (int, float))
            and not isinstance(fact.get("value"), bool)
            and math.isfinite(fact["value"])
            and (fact["value"] > 0 if field == "close" else abs(fact["value"]) <= 100)
        )
    if fact_id.startswith("index."):
        key = fact_id.removeprefix("index.").removesuffix(".change_percent")
        yahoo_pattern = YAHOO_INDEX_URLS.get(key)
        return (
            unit == "percent"
            and observed == report_date
            and (
                (fact.get("quality") == "reviewed" and source_url.startswith("https://"))
                or (
                    yahoo_pattern is not None
                    and bool(re.fullmatch(yahoo_pattern, source_url))
                    and fact.get("quality") == "ok"
                    and fact.get("source") == "Yahoo Finance"
                    and fact.get("metric") == "daily_return"
                )
            )
        )
    if fact_id.startswith("treasury."):
        is_level = fact_id.endswith(".level_percent")
        expected_unit = "percent" if is_level else "basis_points"
        expected_metric = "yield_level" if is_level else "yield_change"
        fresh = observed == report_date and fact.get("quality") in {"ok", "reviewed"}
        lagged = (
            isinstance(observed, str) and observed < report_date and fact.get("quality") == "lagged"
        )
        source_valid = (bool(re.fullmatch(TREASURY_URL, source_url)) and fresh) or (
            bool(re.fullmatch(FRED_URL, source_url)) and (fresh or lagged)
        )
        return source_valid and unit == expected_unit and fact.get("metric") == expected_metric
    if fact_id.startswith("cross_asset."):
        parts = fact_id.split(".")
        if len(parts) != 3:
            return False
        _, asset, field = parts
        if asset == "bitcoin_spot":
            return (
                field in {"close", "change_percent"}
                and (str(fact.get("source")), source_url) in BTC_SPOT_SOURCES
                and fact.get("instrument")
                == BTC_SPOT_SOURCES[(str(fact.get("source")), source_url)]
                and fact.get("quality") == "ok"
                and observed == report_date
                and unit == ("USD/bitcoin" if field == "close" else "percent")
                and fact.get("metric")
                == ("crypto_spot_close" if field == "close" else "daily_return")
            )
        url_pattern = YAHOO_URLS.get(asset)
        is_close = field == "close"
        expected_unit = {
            "brent": "USD/barrel",
            "gold": "USD/troy_ounce",
            "silver": "USD/troy_ounce",
            "bitcoin": "USD/bitcoin",
        }.get(asset)
        expected_metric = (
            ("crypto_futures_close" if asset == "bitcoin" else "commodity_close")
            if is_close
            else "daily_return"
        )
        dated_symbol = _dated_futures_symbol(asset, date.fromisoformat(report_date))
        dated_url = f"https://finance.yahoo.com/quote/{dated_symbol}/history/"
        yahoo_source = (
            (url_pattern is not None and bool(re.fullmatch(url_pattern, source_url)))
            or (
                dated_symbol is not None
                and source_url == dated_url
                and f"({dated_symbol})" in str(fact.get("instrument") or "")
            )
        ) and fact.get("source") == "Yahoo Finance"
        legacy_commodity = (
            allow_legacy_commodity
            and asset in LEGACY_COMMODITY_SYMBOLS
            and fact.get("source") == "Yahoo Finance"
            and source_url
            == f"https://finance.yahoo.com/quote/{LEGACY_COMMODITY_SYMBOLS[asset]}/history/"
        )
        return (
            (yahoo_source or legacy_commodity)
            and fact.get("quality") == "ok"
            and observed == report_date
            and unit == (expected_unit if is_close else "percent")
            and fact.get("metric") == expected_metric
        )
    if fact_id.startswith("macro."):
        return bool(re.fullmatch(FRED_URL, source_url))
    return False


def _valid_equity_pairs(  # noqa: PLR0911 - preserve audited validation branches
    facts_by_id: dict[str, dict[str, Any]], payload: dict[str, Any]
) -> bool:
    symbols = {match.group(1) for fact_id in facts_by_id if (match := EQUITY_ID.fullmatch(fact_id))}
    equities_status = payload.get("source_status", {}).get("equities", {})
    if (
        equities_status.get("quality") == "ok"
        and not {symbol.upper() for symbol in symbols} >= CORE_EQUITIES
    ):
        return False
    reviewed_movers = equities_status.get("reviewed_movers", [])
    if not isinstance(reviewed_movers, list):
        return False
    mover_ids = {
        claim_id
        for section in payload.get("sections", [])
        if section.get("key") == "movers"
        for claim_id in section.get("claims", [])
    }
    events = {
        event.get("id"): event for event in payload.get("events", []) if isinstance(event, dict)
    }
    claims = payload.get("claims", [])
    if (
        reviewed_movers
        and payload.get("source_status", {}).get("research", {}).get("quality") != "reviewed"
    ):
        return False
    if any(
        not isinstance(row, dict)
        or not re.fullmatch(r"[A-Z]{1,5}", str(row.get("ticker", "")))
        or row.get("evidence_id") not in mover_ids
        or not (event := events.get(row.get("evidence_id")))
        or not re.fullmatch(
            r"web_(gainers|losers)_(close|intraday|event)", str(event.get("event_type", ""))
        )
        or event.get("quality") != "reviewed"
        or not str(event.get("source_url", "")).startswith("https://")
        or not any(
            isinstance(claim, dict)
            and row["evidence_id"] in claim.get("evidence_ids", [])
            and claim.get("claim") == event.get("actual")
            and event["source_url"] in claim.get("sources", [])
            and claim.get("status") == "accepted"
            and claim.get("confidence") == "confirmed"
            and claim.get("provider") == "source_audit"
            for claim in claims
        )
        for row in reviewed_movers
    ):
        return False
    allowed = CORE_EQUITIES | {row["ticker"] for row in reviewed_movers}
    if {symbol.upper() for symbol in symbols} - allowed:
        return False
    for symbol in symbols:
        close = facts_by_id.get(f"equity.{symbol}.close")
        change = facts_by_id.get(f"equity.{symbol}.change_percent")
        if (
            not close
            or not change
            or any(
                close.get(key) != change.get(key)
                for key in ("observation_date", "source", "source_url", "instrument")
            )
        ):
            return False
    return True


def _valid_rate_and_asset_pairs(facts_by_id: dict[str, dict[str, Any]]) -> bool:
    for tenor in ("2y", "5y", "10y", "30y"):
        level = facts_by_id.get(f"treasury.{tenor}.level_percent")
        change = facts_by_id.get(f"treasury.{tenor}.change_bp")
        if (
            level
            and change
            and any(
                level.get(key) != change.get(key)
                for key in ("observation_date", "source", "source_url")
            )
        ):
            return False
    for asset in (*YAHOO_URLS, "bitcoin_spot"):
        close = facts_by_id.get(f"cross_asset.{asset}.close")
        change = facts_by_id.get(f"cross_asset.{asset}.change_percent")
        if bool(close) != bool(change):
            return False
        if (
            close
            and change
            and any(
                close.get(key) != change.get(key)
                for key in ("observation_date", "source", "source_url", "instrument")
            )
        ):
            return False
    return True


def _valid_sourced_fact_date(  # noqa: PLR0911 - preserve audited validation branches
    payload: dict[str, Any],
) -> bool:
    if any(
        str(fact.get("id", "")).startswith("equity.")
        and not EQUITY_ID.fullmatch(str(fact.get("id")))
        for fact in payload["facts"]
    ):
        return False
    if not any(
        fact.get("id") in FACT_LABELS or EQUITY_ID.fullmatch(str(fact.get("id")))
        for fact in payload["facts"]
    ):
        return True
    if not _valid_report_time(payload):
        return False
    report_date = str(payload["run_id"]).removeprefix("daily-")
    known_facts = [
        fact
        for fact in payload["facts"]
        if fact.get("id") in FACT_LABELS or EQUITY_ID.fullmatch(str(fact.get("id")))
    ]
    if not all(_valid_market_fact(fact, report_date) for fact in known_facts):
        return False
    facts_by_id = {fact["id"]: fact for fact in known_facts}
    if not _valid_equity_pairs(facts_by_id, payload):
        return False
    yahoo_indices = [
        fact
        for fact in known_facts
        if fact["id"].startswith("index.") and fact.get("quality") == "ok"
    ]
    if yahoo_indices and {fact["id"] for fact in yahoo_indices} != {
        f"index.{key}.change_percent" for key in YAHOO_INDEX_URLS
    }:
        return False
    return _valid_rate_and_asset_pairs(facts_by_id)


def _read(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("daily report must be an object")
    missing = sorted(REQUIRED_FIELDS.difference(payload))
    if missing:
        raise ValueError(f"daily report missing fields: {', '.join(missing)}")
    if payload["schema_version"] not in {"1.0", "1.1"}:
        raise ValueError("unsupported daily report schema")
    if payload.get("quality_summary", {}).get("status") == "fixture":
        raise ValueError("fixture daily report cannot be published")
    if not _valid_content_hash(payload):
        raise ValueError("daily report content hash mismatch")
    if not _unique_evidence_ids(payload):
        raise ValueError("duplicate daily report evidence IDs")
    serialized = json.dumps(payload, ensure_ascii=False)
    if "API_KEY" in serialized or "auth.json" in serialized or "Bearer " in serialized:
        raise ValueError("credentials detected in daily report")
    if not _valid_claims(payload["claims"]):
        raise ValueError("every daily report claim needs evidence and HTTPS sources")
    if not _valid_sourced_fact_date(payload):
        raise ValueError("daily report market date mismatch")
    if payload["schema_version"] == "1.1":
        validate_news_payload(payload)
    return payload


def _public_manifest(source: Path, manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload = json.loads(source.read_text(encoding="utf-8"))
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != "1.0"
        or manifest.get("publication") != "public"
        or manifest.get("report_file") != "daily_report.json"
        or manifest.get("report_sha256") != hashlib.sha256(source.read_bytes()).hexdigest()
        or manifest.get("run_id") != payload.get("run_id")
        or manifest.get("content_hash") != payload.get("content_hash")
    ):
        raise ValueError("public manifest does not match daily report")
    return manifest


def _select(row: dict[str, Any], names: tuple[str, ...]) -> dict[str, Any]:
    return {name: row[name] for name in names if name in row}


def _public_payload(payload: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    facts = [
        _select(fact, PUBLIC_FACT_FIELDS)
        for fact in payload["facts"]
        if fact.get("id") in FACT_LABELS or EQUITY_ID.fullmatch(str(fact.get("id")))
    ]
    claims = [_select(claim, PUBLIC_CLAIM_FIELDS) for claim in payload["claims"]]
    evidence_ids = {item for claim in claims for item in claim.get("evidence_ids", [])}
    mover_evidence_ids = {
        row["evidence_id"]
        for row in payload.get("source_status", {}).get("equities", {}).get("reviewed_movers", [])
    }
    events = [
        _select(
            event,
            PUBLIC_EVENT_FIELDS
            + (
                "source_time",
                "publication_precision",
                "source_date",
                "source_timezone",
                "time_role",
                "usage",
            )
            if payload["schema_version"] == "1.1"
            else PUBLIC_EVENT_FIELDS
            if event.get("id") in mover_evidence_ids
            else ("id",),
        )
        for event in payload.get("events", [])
        if event.get("id") in evidence_ids
    ]
    result = {
        "schema_version": payload["schema_version"],
        "publication": "public",
        "report_formats": ["md", "txt"],
        "as_of": payload["as_of"],
        "generated_at": payload["generated_at"],
        "run_id": payload["run_id"],
        "sections": [
            _select(section, PUBLIC_SECTION_FIELDS) for section in payload.get("sections", [])
        ],
        "facts": facts,
        "events": events,
        "claims": claims,
        "missing_sources": [
            item for item in payload.get("missing_sources", []) if item in MISSING_LABELS
        ],
        "quality_summary": _select(
            payload.get("quality_summary", {}),
            ("status", "revision", "reviewed_source_cutoff"),
        ),
        "source_status": {
            key: _select(
                payload.get("source_status", {}).get(key, {}),
                ("quality", "reason", "reviewed_movers")
                if key == "equities"
                else ("quality", "reason"),
            )
            for key in (
                "rates",
                "macro",
                "quotes",
                "research",
                "cross_asset",
                "btc_spot",
                "equities",
            )
            if key in payload.get("source_status", {})
        },
        "content_hash": payload.get("content_hash"),
        "source_report_sha256": manifest["report_sha256"],
    }
    if payload["schema_version"] == "1.1":
        quality = payload.get("quality_summary", {})
        if "news_revision" in quality:
            result["quality_summary"]["news_revision"] = _select(
                quality["news_revision"], REVISION_FIELDS
            )
        if "news_revision_history" in quality:
            result["quality_summary"]["news_revision_history"] = [
                _select(item, REVISION_FIELDS + ("result_content_hash",))
                for item in quality["news_revision_history"]
            ]
    return result


def _date(payload: dict[str, Any]) -> str:
    run_id = str(payload["run_id"])
    if re.fullmatch(r"daily-\d{4}-\d{2}-\d{2}", run_id):
        return run_id.removeprefix("daily-")
    return str(payload["as_of"])[:10]
