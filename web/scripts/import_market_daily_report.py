"""Import a validated platform daily report into the public Pages tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

SCHEMA_PREFIX = "1."
DATE_FIELDS = {"as_of", "generated_at", "source_time", "retrieved_at"}
REQUIRED_FIELDS = {"schema_version", "as_of", "generated_at", "run_id", "facts", "claims", "source_status"}
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


FMP_CRYPTO_URL = (
    "https://site.financialmodelingprep.com/developer/docs/stable/cryptocurrency-historical-price-eod-full"
)
BTC_SPOT_SOURCES = {
    ("Financial Modeling Prep", FMP_CRYPTO_URL): "BTC/USD cryptocurrency EOD (FMP BTCUSD)",
    (
        "Data provided by CoinGecko",
        "https://www.coingecko.com/en/api",
    ): "BTC/USD spot at 16:00 ET (CoinGecko bitcoin/USD)",
    ("Kraken", "https://www.kraken.com/prices/bitcoin"): "BTC/USD spot at 16:00 ET (Kraken XBT/USD)",
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
}
ASSET_GAP_LABELS = {
    "brent": "布伦特期货行情",
    "gold": "黄金期货行情",
    "silver": "白银期货行情",
    "bitcoin": "比特币期货行情",
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


def _valid_market_fact(
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
        lagged = isinstance(observed, str) and observed < report_date and fact.get("quality") == "lagged"
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
                and fact.get("instrument") == BTC_SPOT_SOURCES[(str(fact.get("source")), source_url)]
                and fact.get("quality") == "ok"
                and observed == report_date
                and unit == ("USD/bitcoin" if field == "close" else "percent")
                and fact.get("metric") == ("crypto_spot_close" if field == "close" else "daily_return")
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
            and source_url == f"https://finance.yahoo.com/quote/{LEGACY_COMMODITY_SYMBOLS[asset]}/history/"
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


def _valid_equity_pairs(facts_by_id: dict[str, dict[str, Any]], payload: dict[str, Any]) -> bool:
    symbols = {match.group(1) for fact_id in facts_by_id if (match := EQUITY_ID.fullmatch(fact_id))}
    equities_status = payload.get("source_status", {}).get("equities", {})
    if equities_status.get("quality") == "ok" and not CORE_EQUITIES <= {symbol.upper() for symbol in symbols}:
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
    events = {event.get("id"): event for event in payload.get("events", []) if isinstance(event, dict)}
    claims = payload.get("claims", [])
    if reviewed_movers and payload.get("source_status", {}).get("research", {}).get("quality") != "reviewed":
        return False
    if any(
        not isinstance(row, dict)
        or not re.fullmatch(r"[A-Z]{1,5}", str(row.get("ticker", "")))
        or row.get("evidence_id") not in mover_ids
        or not (event := events.get(row.get("evidence_id")))
        or not re.fullmatch(r"web_(gainers|losers)_(close|intraday|event)", str(event.get("event_type", "")))
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
            and any(level.get(key) != change.get(key) for key in ("observation_date", "source", "source_url"))
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


def _valid_sourced_fact_date(payload: dict[str, Any]) -> bool:
    if any(
        str(fact.get("id", "")).startswith("equity.") and not EQUITY_ID.fullmatch(str(fact.get("id")))
        for fact in payload["facts"]
    ):
        return False
    if not any(
        fact.get("id") in FACT_LABELS or EQUITY_ID.fullmatch(str(fact.get("id"))) for fact in payload["facts"]
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
        fact for fact in known_facts if fact["id"].startswith("index.") and fact.get("quality") == "ok"
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
    if not str(payload["schema_version"]).startswith(SCHEMA_PREFIX):
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
        _select(event, PUBLIC_EVENT_FIELDS if event.get("id") in mover_evidence_ids else ("id",))
        for event in payload.get("events", [])
        if event.get("id") in evidence_ids
    ]
    return {
        "schema_version": payload["schema_version"],
        "publication": "public",
        "report_formats": ["md", "txt"],
        "as_of": payload["as_of"],
        "generated_at": payload["generated_at"],
        "run_id": payload["run_id"],
        "sections": [_select(section, PUBLIC_SECTION_FIELDS) for section in payload.get("sections", [])],
        "facts": facts,
        "events": events,
        "claims": claims,
        "missing_sources": [item for item in payload.get("missing_sources", []) if item in MISSING_LABELS],
        "quality_summary": _select(
            payload.get("quality_summary", {}),
            ("status", "revision", "reviewed_source_cutoff"),
        ),
        "source_status": {
            key: _select(
                payload.get("source_status", {}).get(key, {}),
                ("quality", "reason", "reviewed_movers") if key == "equities" else ("quality", "reason"),
            )
            for key in ("rates", "macro", "quotes", "research", "cross_asset", "btc_spot", "equities")
            if key in payload.get("source_status", {})
        },
        "content_hash": payload.get("content_hash"),
        "source_report_sha256": manifest["report_sha256"],
    }


def _date(payload: dict[str, Any]) -> str:
    run_id = str(payload["run_id"])
    if re.fullmatch(r"daily-\d{4}-\d{2}-\d{2}", run_id):
        return run_id.removeprefix("daily-")
    return str(payload["as_of"])[:10]


def _missing_labels(payload: dict[str, Any]) -> list[str]:
    labels = []
    facts = {str(fact.get("id")) for fact in payload.get("facts", [])}
    for item in payload.get("missing_sources", []):
        if item == "cross_asset":
            unavailable = [
                name
                for asset, name in ASSET_GAP_LABELS.items()
                if f"cross_asset.{asset}.close" not in facts
                or f"cross_asset.{asset}.change_percent" not in facts
            ]
            labels.extend(unavailable or [MISSING_LABELS[item]])
        elif item in MISSING_LABELS:
            labels.append(MISSING_LABELS[item])
    return labels


def _fact_category(fact_id: str) -> str:
    for prefix, category in (
        ("index.", "market"),
        ("equity.", "equities"),
        ("treasury.", "rates"),
        ("cross_asset.", "cross_asset"),
        ("macro.", "macro"),
    ):
        if fact_id.startswith(prefix):
            return category
    return ""


def _markdown_source(fact: dict[str, Any]) -> str:
    fact_id = str(fact["id"])
    url = str(fact["source_url"])
    if fact_id.startswith("index."):
        name = "Yahoo Finance" if fact.get("source") == "Yahoo Finance" else "核实报道"
    elif fact_id.startswith("equity."):
        name = str(fact.get("source"))
    elif fact_id.startswith("cross_asset."):
        name = {
            "Financial Modeling Prep": "FMP",
            "Data provided by CoinGecko": "Data provided by CoinGecko",
            "Kraken": "Kraken",
        }.get(fact.get("source"), "Yahoo Finance")
    elif url.startswith("https://home.treasury.gov/"):
        name = "美国财政部"
    else:
        name = "FRED"
    return f"[{name}]({url})"


def _market_table(facts: list[dict[str, Any]], include_references: bool = True) -> list[str]:
    lines = (
        ["| 指数 | 收盘涨跌 | 观测日 | 来源 |", "|---|---:|---|---|"]
        if include_references
        else ["| 指数 | 收盘涨跌 | 观测日 |", "|---|---:|---|"]
    )
    for fact in facts:
        label = FACT_LABELS[fact["id"]][0].removesuffix("日涨跌").strip()
        lines.append(
            f"| {label} | {float(fact['value']):+.2f}% | {fact['observation_date']} |"
            + (f" {_markdown_source(fact)} |" if include_references else "")
        )
    return lines


def _equities_table(facts: list[dict[str, Any]], include_references: bool = True) -> list[str]:
    lines = (
        ["| 股票 | 收盘价 | 日涨跌 | 观测日 | 来源 |", "|---|---:|---:|---|---|"]
        if include_references
        else ["| 股票 | 收盘价 | 日涨跌 | 观测日 |", "|---|---:|---:|---|"]
    )
    by_id = {fact["id"]: fact for fact in facts}
    for fact in facts:
        match = EQUITY_ID.fullmatch(fact["id"])
        if not match or match.group(2) != "close":
            continue
        change = by_id[f"equity.{match.group(1)}.change_percent"]
        lines.append(
            f"| {fact['instrument']} | {float(fact['value']):,.2f} 美元 | "
            f"{float(change['value']):+.2f}% | {fact['observation_date']} |"
            + (f" {_markdown_source(fact)} |" if include_references else "")
        )
    return lines


def _rates_table(facts: list[dict[str, Any]], include_references: bool = True) -> list[str]:
    lines = (
        ["| 美债期限 | 收益率水平 | 日变动 | 观测日 | 来源 |", "|---|---:|---:|---|---|"]
        if include_references
        else ["| 美债期限 | 收益率水平 | 日变动 | 观测日 |", "|---|---:|---:|---|"]
    )
    names = {"2y": "2 年期", "5y": "5 年期", "10y": "10 年期", "30y": "30 年期"}
    by_id = {fact["id"]: fact for fact in facts}
    for tenor, name in names.items():
        level = by_id.get(f"treasury.{tenor}.level_percent")
        change = by_id.get(f"treasury.{tenor}.change_bp")
        if not level and not change:
            continue
        level_text = f"{float(level['value']):.2f}%" if level else "—"
        change_text = f"{float(change['value']):+.2f} bp" if change else "—"
        fact = change if change is not None else level
        if fact is None:
            continue
        lines.append(
            f"| {name} | {level_text} | {change_text} | "
            f"{fact['observation_date']} |" + (f" {_markdown_source(fact)} |" if include_references else "")
        )
    return lines


def _cross_asset_table(facts: list[dict[str, Any]], include_references: bool = True) -> list[str]:
    lines = (
        ["| 品种 | 价格 | 日涨跌 | 观测日 | 来源 |", "|---|---:|---:|---|---|"]
        if include_references
        else ["| 品种 | 价格 | 日涨跌 | 观测日 |", "|---|---:|---:|---|"]
    )
    for fact in facts:
        if not fact["id"].endswith(".close"):
            continue
        _, asset, _ = fact["id"].split(".")
        change = next((row for row in facts if row["id"] == f"cross_asset.{asset}.change_percent"), None)
        if change is None:
            continue
        label = FACT_LABELS[fact["id"]][0].removesuffix("收盘")
        unit = FACT_LABELS[fact["id"]][1]
        lines.append(
            f"| {label} | {float(fact['value']):,.2f} {unit} | {float(change['value']):+.2f}% | "
            f"{fact['observation_date']} |" + (f" {_markdown_source(fact)} |" if include_references else "")
        )
    return lines


def _macro_table(facts: list[dict[str, Any]], include_references: bool = True) -> list[str]:
    lines = (
        ["| 数据 | 数值 | 观测日 | 来源 |", "|---|---:|---|---|"]
        if include_references
        else ["| 数据 | 数值 | 观测日 |", "|---|---:|---|"]
    )
    for fact in facts:
        label, unit = FACT_LABELS[fact["id"]]
        lines.append(
            f"| {label} | {float(fact['value']):.2f}{unit} | {fact['observation_date']} |"
            + (f" {_markdown_source(fact)} |" if include_references else "")
        )
    return lines


def _markdown_fact_lines(
    payload: dict[str, Any],
    section: str,
    include_references: bool = True,
    *,
    allow_legacy_commodity: bool = False,
) -> list[str]:
    grouped = []
    for fact in payload["facts"]:
        fact_id = str(fact.get("id") or "")
        if _fact_category(fact_id) != section or (
            fact_id not in FACT_LABELS and not EQUITY_ID.fullmatch(fact_id)
        ):
            continue
        value = fact.get("value")
        observed = str(fact.get("observation_date") or "")
        is_valid = (
            not isinstance(value, bool)
            and isinstance(value, (int, float))
            and math.isfinite(value)
            and re.fullmatch(r"\d{4}-\d{2}-\d{2}", observed)
            and _valid_market_fact(fact, _date(payload), allow_legacy_commodity=allow_legacy_commodity)
        )
        if not is_valid:
            raise ValueError(f"invalid sourced market fact: {fact_id}")
        grouped.append(fact)
    if not grouped:
        return []
    renderers = {
        "market": _market_table,
        "equities": _equities_table,
        "rates": _rates_table,
        "cross_asset": _cross_asset_table,
        "macro": _macro_table,
    }
    return renderers[section](grouped, include_references)


def _source_status_lines(statuses: dict[str, Any], include_references: bool = True) -> list[str]:
    if not statuses:
        return []
    lines = ["## 数据质量与核验说明", "", "| 数据链路 | 状态 | 说明 |", "|---|---|---|"]
    for key, label in SOURCE_STATUS_LABELS.items():
        status = statuses.get(key)
        if not isinstance(status, dict):
            continue
        quality = SOURCE_QUALITY_LABELS.get(status.get("quality"), "未确认")
        reason = SOURCE_REASON_LABELS.get(status.get("reason"), "详见逐项观测日与来源")
        lines.append(f"| {label} | {quality} | {reason} |")
    return (
        [*lines, "", "证据编号对应已审阅材料；公开报告不包含私有核验工作底稿。", ""]
        if include_references
        else [*lines, ""]
    )


def _claim_markdown_lines(claim: dict[str, Any], include_references: bool) -> list[str]:
    lines = [f"- {claim['claim']}"]
    if include_references:
        evidence = ", ".join(f"`{item}`" for item in claim["evidence_ids"])
        sources = "、".join(f"[来源{index}]({url})" for index, url in enumerate(claim["sources"], start=1))
        lines.extend([f"  - 证据：{evidence}", f"  - {sources}"])
    return lines


def _markdown_header(payload: dict[str, Any], include_references: bool) -> list[str]:
    lines = [f"# 美股市场日报（{_date(payload)}）", ""]
    if include_references:
        lines.extend(
            [
                f"数据状态：{payload.get('quality_summary', {}).get('status', 'unknown')}",
                f"报告生成时间：{payload['as_of']}（美东报告日 {_date(payload)}）",
                "",
            ]
        )
        cutoff = payload.get("quality_summary", {}).get("reviewed_source_cutoff")
        if cutoff:
            lines.extend([f"新闻资料截止：{cutoff}。", ""])
    if payload.get("quality_summary", {}).get("revision") == "historical_backfill":
        lines.extend(
            [
                "历史补报：按指定交易日数据事后重建，生成时间不代表当日已发布。"
                if include_references
                else "事后整理",
                "",
            ]
        )
    return lines


def _markdown(
    payload: dict[str, Any],
    include_references: bool = True,
    *,
    allow_legacy_commodity: bool = False,
) -> str:
    lines = _markdown_header(payload, include_references)
    gaps = _missing_labels(payload)
    if gaps:
        lines.extend([f"尚缺：{'、'.join(gaps)}。", ""])
    grouped = _group_claims(payload)
    report_sections = (
        ("market", "美股市场表现"),
        ("equities", "美股个股行情"),
        ("movers", "主要个股"),
        ("rates", "美债收益率"),
        ("cross_asset", "布伦特、金银与比特币"),
        ("drivers", "市场驱动因素"),
        ("macro", "经济数据与美联储动态"),
        ("company_news", "公司新闻"),
    )
    for key, title in report_sections:
        lines.extend([f"## {title}", ""])
        facts = _markdown_fact_lines(
            payload, key, include_references, allow_legacy_commodity=allow_legacy_commodity
        )
        lines.extend(facts)
        for claim in grouped.get(key, []):
            lines.extend(_claim_markdown_lines(claim, include_references))
        if not facts and not grouped.get(key, []):
            lines.append("暂无经核实内容。")
        lines.append("")
    if grouped["other"]:
        lines.extend(["## 其他已核实内容", ""])
        for claim in grouped["other"]:
            lines.extend(_claim_markdown_lines(claim, include_references))
    source_status = (
        _source_status_lines(payload.get("source_status", {}), include_references)
        if include_references
        else []
    )
    lines.extend(source_status)
    if not source_status:
        lines.append("")
    return "\n".join(lines)


def _text_fact_lines(payload: dict[str, Any], prefix: str) -> list[str]:
    facts = {fact["id"]: fact for fact in payload["facts"] if fact.get("id") in FACT_LABELS}
    lines = []
    for fact_id, (label, unit) in FACT_LABELS.items():
        if not fact_id.startswith(prefix) or fact_id not in facts:
            continue
        fact = facts[fact_id]
        signed = fact_id.startswith("index.") or fact_id.endswith((".change_bp", ".change_percent"))
        value = f"{fact['value']:+.2f}" if signed else f"{fact['value']:.2f}"
        suffix = unit if unit == "%" else f" {unit}"
        lines.extend(
            [
                f"- {label}：{value}{suffix}（观测日 {fact['observation_date']}）",
                f"  来源：{fact['source_url']}",
            ]
        )
    return lines


def _group_claims(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {key: [] for key in RESEARCH_SECTION_TITLES}
    groups["other"] = []
    section_ids = {
        section.get("key"): set(section.get("claims", []))
        for section in payload.get("sections", [])
        if isinstance(section, dict) and isinstance(section.get("claims"), list)
    }
    for claim in payload["claims"]:
        key = next(
            (
                key
                for key in RESEARCH_SECTION_TITLES
                if section_ids.get(key, set()).intersection(claim["evidence_ids"])
            ),
            "other",
        )
        groups[key].append(claim)
    return groups


def _text_claim_lines(claims: list[dict[str, Any]]) -> list[str]:
    if not claims:
        return ["- 暂无经核实内容。"]
    lines = []
    for index, claim in enumerate(claims, start=1):
        lines.extend([f"{index}、{claim['claim']}", *(f"   来源：{url}" for url in claim["sources"])])
    return lines


def _text_report(payload: dict[str, Any]) -> str:
    report_date = _date(payload)
    grouped = _group_claims(payload)
    market_facts = _text_fact_lines(payload, "index.")
    equity_facts = [
        f"- {fact['instrument']}：{float(fact['value']):,.2f} 美元，"
        f"{float(next(row for row in payload['facts'] if row['id'] == fact['id'].removesuffix('.close') + '.change_percent')['value']):+.2f}%"
        f"（观测日 {fact['observation_date']}）\n  来源：{fact['source_url']}"
        for fact in payload["facts"]
        if EQUITY_ID.fullmatch(str(fact.get("id"))) and fact["id"].endswith(".close")
    ]
    treasury_facts = _text_fact_lines(payload, "treasury.")
    macro_facts = _text_fact_lines(payload, "macro.")
    cross_asset_facts = _text_fact_lines(payload, "cross_asset.")
    lines = [
        f"美股市场日报｜{report_date} 美东报告日",
        f"报告生成时间：{payload['as_of']}；逐项显示原始观测日。",
        "",
        "一、美股市场表现",
        *(market_facts or ["- 暂无经核实指数行情。"]),
        *(_text_claim_lines(grouped["market"]) if grouped["market"] else []),
        "",
        "二、重点个股",
        *equity_facts,
        *_text_claim_lines(grouped["movers"]),
        "",
        "三、美债收益率",
        *(treasury_facts or ["- 暂无经核实的美债收益率水平或日变动。"]),
        "",
        "四、跨资产行情",
        *(cross_asset_facts or ["- 暂无经核实的跨资产行情。"]),
        "",
        "五、市场驱动因素",
        *_text_claim_lines(grouped["drivers"]),
        "",
        "六、经济数据与美联储动态",
        *(macro_facts or ["- 暂无经核实利率与宏观数据。"]),
        *(_text_claim_lines(grouped["macro"]) if grouped["macro"] else []),
        "",
        "七、公司新闻",
        *_text_claim_lines(grouped["company_news"]),
        "",
    ]
    cutoff = payload.get("quality_summary", {}).get("reviewed_source_cutoff")
    if cutoff:
        lines[2:2] = [f"新闻资料截止：{cutoff}。"]
    if payload.get("quality_summary", {}).get("revision") == "historical_backfill":
        lines[2:2] = ["历史补报：本次事后重建，非当日已发布报告。"]
    if grouped["other"]:
        lines.extend(["八、其他已核实内容", *_text_claim_lines(grouped["other"])])
    gaps = _missing_labels(payload)
    if gaps:
        lines.extend(["", f"尚缺：{'、'.join(gaps)}。"])
    lines.extend(["", "风险提示：市场有风险，投资需谨慎。", ""])
    return "\n".join(lines)


def import_report(source: Path, root: Path, manifest_path: Path) -> str:
    try:
        from .public_paths import public_snapshot_root
    except ImportError:
        from public_paths import public_snapshot_root

    manifest = _public_manifest(source, manifest_path)
    payload = _public_payload(_read(source), manifest)
    report_date = _date(payload)
    public_root = public_snapshot_root(root)
    data_path = public_root / "data/market_daily_report.json"
    history_path = public_root / "data/market_daily_reports.json"
    report_path = public_root / f"reports/{report_date}-market-daily.md"
    reading_path = public_root / f"reports/{report_date}-market-daily-no-citations.md"
    text_path = public_root / f"reports/{report_date}-market-daily.txt"
    if history_path.is_file():
        previous = json.loads(history_path.read_text(encoding="utf-8"))
        if previous.get("schema_version") != "market_intel_pages.us_daily_history.v1" or not isinstance(
            previous.get("reports"), list
        ):
            raise ValueError("invalid US daily history index")
        reports = previous["reports"]
    elif data_path.is_file():
        reports = [json.loads(data_path.read_text(encoding="utf-8"))]
    else:
        reports = []
    by_date = {_date(row): row for row in reports}
    older = by_date.get(report_date)
    if older and datetime.fromisoformat(older["generated_at"]) > datetime.fromisoformat(
        payload["generated_at"]
    ):
        raise ValueError("older US daily revision cannot replace newer report")
    by_date[report_date] = payload
    dates = sorted(by_date, reverse=True)[:5]
    if report_date not in dates:
        raise ValueError("US daily report falls outside five-date public window")
    history = {
        "schema_version": "market_intel_pages.us_daily_history.v1",
        "reports": [by_date[day] for day in dates],
    }
    data_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    data_path.write_text(
        json.dumps(history["reports"][0], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report_path.write_text(_markdown(payload), encoding="utf-8")
    reading_path.write_text(_markdown(payload, include_references=False), encoding="utf-8")
    text_path.write_text(_text_report(payload), encoding="utf-8")
    return report_date


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()
    print(import_report(args.input, args.root, args.manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
