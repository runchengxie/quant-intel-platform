"""Cross-market data fetching and US→A-share concept mapping.

Data sources:
    - yfinance: US stock prices (Mag7 + semis + ETFs), commodities, DXY
    - FRED: VIX (VIXCLS), 10Y Treasury (DGS10); public CSV works without a key
    - CBOE public history CSV: VIX / VVIX daily closes
    - AAII: weekly US retail investor sentiment (bull/bear/neutral)
    - CBOE: VIX from FRED as fear gauge (old put/call CSV discontinued 2019)

All fetchers degrade gracefully. A single failure does not block the pipeline.
Proxy: honours HTTP_PROXY / HTTPS_PROXY env vars for US-bound requests.
"""

from __future__ import annotations

import csv
import io
import json
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import requests

from .cross_market_fetcher import Fetcher, FredAdapter
from .cross_market_summary import generate_summary as _generate_summary
from .global_leadlag import US_TO_A_MAPPING, aggregate_concept_signals, fetch_symbols
from .korea_market import (
    KOREA_INDEX_SYMBOL,
    KOREA_SYMBOLS,
    compute_korea_signal,
    fetch_korea_daily_quotes,
)

# Symbols to fetch (US mega-cap/semis + Japan/Korea semis + benchmark ETFs)
US_SYMBOLS = fetch_symbols()

# ── Commodities → A-share concept mapping ─────────────────────
COMMODITY_TO_A_MAPPING: dict[str, list[str]] = {
    "GC=F": ["黄金概念", "贵金属", "珠宝首饰"],
    "SLV": ["白银概念", "贵金属"],
    "GLD": ["黄金概念", "贵金属"],
}

# Commodity symbols to fetch
COMMODITY_SYMBOLS = ["GC=F", "SLV", "GLD"]

# ── Macro indicators ──────────────────────────────────────────
# FRED series mapping: yfinance symbol → FRED series ID
_FRED_MACRO_SERIES: dict[str, str] = {
    "^VIX": "VIXCLS",
    "^TNX": "DGS10",
}
CBOE_DAILY_PRICE_BASE = "https://cdn.cboe.com/api/global/us_indices/daily_prices"
_CBOE_MACRO_SERIES: dict[str, tuple[str, str]] = {
    "^VIX": ("VIX_History.csv", "CLOSE"),
    "^VVIX": ("VVIX_History.csv", "VVIX"),
}
# DXY stays on yfinance (no free FRED equivalent for ICE DXY index)
_DXY_SYMBOLS = ["DX-Y.NYB"]

MACRO_LABELS = {
    "DX-Y.NYB": "DXY 美元指数",
    "^VIX": "VIX 恐慌指数",
    "^VVIX": "VVIX 波动率波动率指数",
    "^TNX": "10Y 美债收益率",
}

FRED_TIMEOUT = 15
CBOE_TIMEOUT = 15


@dataclass
class CrossMarketResult:
    """Aggregated cross-market data for one trading day."""

    date: str = ""
    us_stocks: dict[str, dict] = field(default_factory=dict)
    commodities: dict[str, dict] = field(default_factory=dict)
    macros: dict[str, dict] = field(default_factory=dict)
    aaii: dict | None = None
    cboe: dict | None = None
    mapping: list[dict] = field(default_factory=list)
    global_lead_lag: list[dict] = field(default_factory=list)
    commodity_mapping: list[dict] = field(default_factory=list)
    korea_quotes: dict[str, dict] = field(default_factory=dict)
    korea_preopen: dict = field(default_factory=dict)
    korea_overnight: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "us_stocks": self.us_stocks,
            "commodities": self.commodities,
            "macros": self.macros,
            "aaii_sentiment": self.aaii,
            "cboe_putcall": self.cboe,
            "concept_mapping": self.mapping,
            "global_lead_lag": self.global_lead_lag,
            "commodity_concept_mapping": self.commodity_mapping,
            "korea_quotes": self.korea_quotes,
            "korea_preopen": self.korea_preopen,
            "korea_overnight": self.korea_overnight,
            "errors": self.errors,
        }


# ═══════════════════════════════════════════════════════════════
# Fetchers
# ═══════════════════════════════════════════════════════════════


def _fred_csv(
    series_id: str,
    *,
    fetcher: Fetcher | None = None,
) -> tuple[float, float, str]:
    """Fetch the latest two FRED observations through the shared source policy.

    Returns (latest_value, previous_value, date_string).

    ``fetcher`` is optional and defaults to ``FredAdapter()`` (lazy load of
    daily_messenger.etl.fetchers.fred). Injecting a fetcher is intended for
    testing only.
    """
    fetcher = fetcher or FredAdapter()
    observations = fetcher.fetch_observations(
        series_id,
        start="2026-01-01",
        limit=2,
        timeout=FRED_TIMEOUT,
    )
    if len(observations) < 2:
        raise RuntimeError(f"FRED {series_id}: only {len(observations)} data rows")
    previous, latest = observations[-2:]
    return latest.value, previous.value, latest.date


def _cboe_history_csv(filename: str, value_column: str) -> tuple[float, float, str]:
    """Fetch latest two close values from Cboe public daily history CSV."""
    url = f"{CBOE_DAILY_PRICE_BASE}/{filename}"
    resp = requests.get(url, timeout=CBOE_TIMEOUT)
    resp.raise_for_status()
    reader = csv.DictReader(io.StringIO(resp.text))
    rows: list[tuple[str, float]] = []
    for row in reader:
        raw_date = str(row.get("DATE") or "").strip()
        raw_value = str(row.get(value_column) or "").strip()
        if not raw_date or not raw_value:
            continue
        try:
            value = float(raw_value)
            parsed_date = datetime.strptime(raw_date, "%m/%d/%Y").date().isoformat()
        except ValueError:
            continue
        rows.append((parsed_date, value))
    if len(rows) < 2:
        raise RuntimeError(f"Cboe {filename}: only {len(rows)} data rows")
    prev_date, prev_val = rows[-2]
    latest_date, latest_val = rows[-1]
    if latest_date <= prev_date:
        raise RuntimeError(f"Cboe {filename}: latest date is not newer than previous date")
    return latest_val, prev_val, latest_date


def _fetch_us_stocks() -> dict[str, Any]:
    """Fetch external equity closing prices and % change via yfinance."""
    try:
        import yfinance as yf

        data = yf.download(US_SYMBOLS, period="5d", progress=False, auto_adjust=False)
        result: dict[str, dict] = {}
        for sym in US_SYMBOLS:
            try:
                cs = data["Close"][sym].dropna()
                if len(cs) >= 2:
                    latest = float(cs.iloc[-1])
                    prev = float(cs.iloc[-2])
                    pct = (latest - prev) / prev * 100 if prev != 0 else 0.0
                    result[sym] = {
                        "close": round(latest, 2),
                        "pct_chg": round(pct, 2),
                        "as_of_date": cs.index[-1].date().isoformat(),
                    }
                else:
                    result[sym] = {"error": "insufficient data"}
            except Exception:
                result[sym] = {"error": "no data"}
        return result
    except Exception as e:
        return {"error": f"yfinance failed: {e}"}


def _fetch_aaii() -> dict | None:
    """Fetch latest AAII sentiment survey via daily-messenger fetcher."""
    try:
        from daily_messenger.etl.fetchers import aaii_sentiment

        result, status = aaii_sentiment.fetch()
        if not status.ok or not result:
            return None
        aaii_data = result.get("aaii", {})
        if not aaii_data:
            return None
        return {
            "week": aaii_data.get("week"),
            "bullish_pct": aaii_data.get("bullish_pct"),
            "neutral_pct": aaii_data.get("neutral_pct"),
            "bearish_pct": aaii_data.get("bearish_pct"),
            "bull_bear_spread": aaii_data.get("bull_bear_spread"),
        }
    except Exception:
        return None


def _fetch_cboe() -> dict | None:
    """Fetch VIX from FRED as fear gauge under the legacy CBOE field.

    The old CBOE put/call CSV feed stopped updating in 2019, so live
    snapshots must not fall back to it and silently publish stale data.
    """
    try:
        vix_val, vix_prev, vix_date = _fred_csv("VIXCLS")
        vix_pct = (vix_val - vix_prev) / vix_prev * 100 if vix_prev != 0 else 0.0
        return {
            "as_of_date": vix_date,
            "vix": round(vix_val, 2),
            "vix_pct_chg": round(vix_pct, 2),
            "source": "fred_vixcls",
        }
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════
# Mapping logic
# ═══════════════════════════════════════════════════════════════


def _compute_concept_mapping(
    us_stocks: dict[str, dict],
    mapping_table: dict[str, list[str]] = US_TO_A_MAPPING,
) -> list[dict]:
    """Aggregate external equity moves into A-share concept signals."""
    return aggregate_concept_signals(us_stocks, mapping_table=mapping_table)


def _fetch_commodities() -> dict[str, Any]:
    """Fetch commodity prices via yfinance (GC=F gold futures, SLV silver, GLD gold ETF)."""
    try:
        import yfinance as yf

        data = yf.download(COMMODITY_SYMBOLS, period="5d", progress=False, auto_adjust=False)
        result: dict[str, dict] = {}
        for sym in COMMODITY_SYMBOLS:
            try:
                cs = data["Close"][sym].dropna()
                if len(cs) >= 2:
                    latest = float(cs.iloc[-1])
                    prev = float(cs.iloc[-2])
                    pct = (latest - prev) / prev * 100 if prev != 0 else 0.0
                    result[sym] = {"close": round(latest, 2), "pct_chg": round(pct, 2)}
                else:
                    result[sym] = {"error": "insufficient data"}
            except Exception:
                result[sym] = {"error": "no data"}
        return result
    except Exception as e:
        return {"error": f"yfinance commodities failed: {e}"}


def _fetch_korea_signals(trade_date: str) -> tuple[dict[str, dict], dict, dict]:
    """Fetch keyless Korea daily data and expose two A-share warning windows.

    The current free-provider fallback is daily, so both windows are explicitly
    marked as ``daily-proxy``. A future intraday provider can feed the same
    ``compute_korea_signal`` contract without changing report consumers.
    """
    target = _parse_yyyymmdd(trade_date) or date.today()
    start = (target - timedelta(days=7)).isoformat()
    end = target.isoformat()
    quotes = fetch_korea_daily_quotes(
        [*KOREA_SYMBOLS, KOREA_INDEX_SYMBOL],
        start,
        end,
    )
    return (
        quotes,
        compute_korea_signal(quotes, window="preopen"),
        compute_korea_signal(quotes, window="overnight"),
    )


def _compute_commodity_mapping(
    commodities: dict[str, dict],
    mapping_table: dict[str, list[str]] = COMMODITY_TO_A_MAPPING,
) -> list[dict]:
    """Aggregate commodity moves into A-share concept signals."""
    concept_scores: dict[str, dict] = {}
    for sym, info in commodities.items():
        if "pct_chg" not in info or sym not in mapping_table:
            continue
        pct = info["pct_chg"]
        for concept in mapping_table[sym]:
            if concept not in concept_scores:
                concept_scores[concept] = {"sum_pct": 0.0, "count": 0, "drivers": []}
            concept_scores[concept]["sum_pct"] += pct
            concept_scores[concept]["count"] += 1
            concept_scores[concept]["drivers"].append(f"{sym} {pct:+.1f}%")

    ranked = []
    for concept, data in concept_scores.items():
        avg = data["sum_pct"] / data["count"]
        signal = "bullish" if avg > 1 else "bearish" if avg < -1 else "neutral"
        ranked.append(
            {
                "concept": concept,
                "avg_pct_chg": round(avg, 2),
                "signal": signal,
                "drivers": data["drivers"],
            }
        )
    ranked.sort(key=lambda x: x["avg_pct_chg"], reverse=True)
    return ranked


def _fetch_macros() -> dict[str, dict]:
    """Fetch macro indicators: VIX/VVIX from Cboe, 10Y from FRED, DXY from yfinance."""
    result: dict[str, dict] = {}

    # ── VIX + 10Y from FRED (free, no API key) ─────────────
    for sym, series_id in _FRED_MACRO_SERIES.items():
        try:
            latest_val, prev_val, as_of = _fred_csv(series_id)
            pct = (latest_val - prev_val) / prev_val * 100 if prev_val != 0 else 0.0
            label = MACRO_LABELS.get(sym, sym)
            result[sym] = {
                "label": label,
                "close": round(latest_val, 2),
                "pct_chg": round(pct, 2),
                "source": "fred",
                "as_of_date": as_of,
            }
        except Exception as e:
            result[sym] = {"error": f"fred:{e}"}

    # ── VIX + VVIX from Cboe public history CSV ────────────
    for sym, (filename, value_column) in _CBOE_MACRO_SERIES.items():
        try:
            latest_val, prev_val, as_of = _cboe_history_csv(filename, value_column)
            pct = (latest_val - prev_val) / prev_val * 100 if prev_val != 0 else 0.0
            result[sym] = {
                "label": MACRO_LABELS.get(sym, sym),
                "close": round(latest_val, 2),
                "pct_chg": round(pct, 2),
                "source": "cboe_history",
                "as_of_date": as_of,
            }
        except Exception as e:
            if sym not in result:
                result[sym] = {"error": f"cboe:{e}"}
            else:
                result[sym]["cboe_error"] = str(e)

    # ── DXY from yfinance (no free FRED ICE DXY) ───────────
    try:
        import yfinance as yf

        data = yf.download(_DXY_SYMBOLS, period="5d", progress=False, auto_adjust=False)
        cs = data["Close"]["DX-Y.NYB"].dropna()
        if len(cs) >= 2:
            latest = float(cs.iloc[-1])
            prev = float(cs.iloc[-2])
            pct = (latest - prev) / prev * 100 if prev != 0 else 0.0
            result["DX-Y.NYB"] = {
                "label": "DXY 美元指数",
                "close": round(latest, 2),
                "pct_chg": round(pct, 2),
                "source": "yfinance",
            }
        else:
            result["DX-Y.NYB"] = {"error": "insufficient data"}
    except Exception as e:
        result["DX-Y.NYB"] = {"error": f"yfinance:{e}"}

    return result


# ═══════════════════════════════════════════════════════════════
# Snapshot fallback: read from GH Actions data-snapshots/ first
# ═══════════════════════════════════════════════════════════════

# Path relative to market-intel repo root
_DATA_SNAPSHOTS_ROOT = Path(__file__).resolve().parents[2] / "data-snapshots"
_SNAPSHOT_MAX_AGE_DAYS = 1
_WEEKEND_SNAPSHOT_MAX_AGE_DAYS = 3
_MACRO_MAX_AGE_DAYS = 3


def _parse_yyyymmdd(value: str) -> date | None:
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except (TypeError, ValueError):
        return None


def _parse_iso_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _max_snapshot_age_days(target_dt: date) -> int:
    if target_dt.weekday() in (0, 5, 6):
        return _WEEKEND_SNAPSHOT_MAX_AGE_DAYS
    return _SNAPSHOT_MAX_AGE_DAYS


def _find_snapshot_path(trade_date: str) -> tuple[Path, bool] | None:
    """Find the best matching snapshot file for a given trade date.

    Priority:
    1. Exact date: data-snapshots/cross-market/YYYY-MM-DD.json
    2. Latest symlink: data-snapshots/latest/cross_market_snapshot.json
    """
    date_dash = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"

    # 1) Exact date snapshot
    snapshot_root = (
        Path(os.environ["CROSS_MARKET_SNAPSHOT_ROOT"]).expanduser()
        if os.environ.get("CROSS_MARKET_SNAPSHOT_ROOT")
        else _DATA_SNAPSHOTS_ROOT
    )
    exact = snapshot_root / "cross-market" / f"{date_dash}.json"
    if exact.exists():
        return exact, True

    # 2) Latest symlink
    latest = snapshot_root / "latest" / "cross_market_snapshot.json"
    if latest.exists():
        return latest, False

    return None


def _is_snapshot_fresh(snapshot: dict, trade_date: str) -> bool:
    """Check if snapshot date matches or is acceptably recent."""
    snap_date = snapshot.get("date", "")
    if snap_date == trade_date:
        return True
    snap_dt = _parse_yyyymmdd(str(snap_date))
    target_dt = _parse_yyyymmdd(trade_date)
    if snap_dt is None or target_dt is None:
        return False
    age = (target_dt - snap_dt).days
    return 0 <= age <= _max_snapshot_age_days(target_dt)


def _annotate_freshness(data: dict[str, Any], trade_date: str) -> dict[str, Any]:
    """Attach freshness warnings for fields that can lag silently."""
    target_dt = _parse_yyyymmdd(trade_date) or date.today()
    warnings = list(data.get("_freshness_warnings") or [])

    if str(data.get("date") or "") != trade_date:
        warnings.append(f"cross-market snapshot date is {data.get('date')}, requested {trade_date}")

    macros = data.get("macros")
    if isinstance(macros, dict):
        for symbol in ("^VIX", "^VVIX", "^TNX"):
            raw = macros.get(symbol)
            if not isinstance(raw, dict):
                continue
            as_of = _parse_iso_date(raw.get("as_of_date"))
            if as_of is None:
                continue
            stale_days = (target_dt - as_of).days
            raw["stale_days"] = stale_days
            if stale_days > _MACRO_MAX_AGE_DAYS:
                label = raw.get("label", symbol)
                warnings.append(f"{label} 快照日期为 {as_of.isoformat()}，滞后 {stale_days} 天")

    cboe = data.get("cboe_putcall")
    if isinstance(cboe, dict):
        as_of = _parse_iso_date(cboe.get("as_of_date"))
        if as_of is not None:
            stale_days = (target_dt - as_of).days
            cboe["stale_days"] = stale_days
            if stale_days > _MACRO_MAX_AGE_DAYS:
                warnings.append(f"VIX 恐贪指标快照日期为 {as_of.isoformat()}，滞后 {stale_days} 天")

    if warnings:
        data["_freshness_warnings"] = sorted({str(item) for item in warnings})
    return data


def _load_snapshot(trade_date: str) -> dict[str, Any] | None:
    """Try to load cross-market data from GH Actions snapshot.

    Returns None if no usable snapshot is found.
    """
    found = _find_snapshot_path(trade_date)
    if found is None:
        return None
    path, is_exact = found

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    if is_exact and data.get("date") != trade_date:
        return None

    if not _is_snapshot_fresh(data, trade_date):
        return None

    if "global_lead_lag" not in data and isinstance(data.get("us_stocks"), dict):
        data["global_lead_lag"] = aggregate_concept_signals(data["us_stocks"])

    # Inject source marker
    data["_source"] = "data-snapshots"
    return _annotate_freshness(data, trade_date)


# ═══════════════════════════════════════════════════════════════
# Pipeline step
# ═══════════════════════════════════════════════════════════════


def _fetch_cboe_into(result: CrossMarketResult) -> None:
    """Fetch CBOE / VIX fear gauge into the result, non-blocking."""
    try:
        result.cboe = _fetch_cboe()
        if result.cboe is None:
            result.errors.append("cboe: FRED VIX unavailable")
    except Exception as e:
        result.errors.append(f"cboe: {e}")


def _map_us_into(result: CrossMarketResult) -> None:
    """Aggregate US-stock moves into A-share concept mapping, non-blocking."""
    try:
        if result.us_stocks and not isinstance(
            result.us_stocks.get(list(result.us_stocks.keys())[0] if result.us_stocks else ""),
            str,
        ):
            result.mapping = aggregate_concept_signals(result.us_stocks)
            result.global_lead_lag = result.mapping
    except Exception as e:
        result.errors.append(f"mapping: {e}")


def _map_commodities_into(result: CrossMarketResult) -> None:
    """Aggregate commodity moves into A-share concept mapping, non-blocking."""
    try:
        if result.commodities and not isinstance(
            result.commodities.get(
                list(result.commodities.keys())[0] if result.commodities else ""
            ),
            str,
        ):
            result.commodity_mapping = _compute_commodity_mapping(result.commodities)
    except Exception as e:
        result.errors.append(f"commodity_mapping: {e}")


def run(trade_date: str | None = None) -> dict[str, Any]:
    """Run the full cross-market pipeline.

    Strategy:
    1. Try GH Actions data-snapshots/ first (fast, no proxy needed)
    2. Fall back to live fetch (yfinance/FRED/AAII) if snapshot unavailable
    Set CROSS_MARKET_FORCE_LIVE=1 to skip snapshot and always fetch live.

    Returns a dict suitable for inclusion in the morning manifest.
    All failures are non-blocking. Partial results are returned with errors.
    """
    if trade_date is None:
        trade_date = date.today().strftime("%Y%m%d")

    # ── Snapshot-first strategy ────────────────────────────────
    snapshot: dict[str, Any] | None = None
    if not os.environ.get("CROSS_MARKET_FORCE_LIVE"):
        snapshot = _load_snapshot(trade_date)
        if snapshot is not None and not snapshot.get("_freshness_warnings"):
            return snapshot

    # ── Live fetch (fallback) ──────────────────────────────────
    result = CrossMarketResult(date=trade_date)

    # US stocks (yfinance)
    try:
        result.us_stocks = _fetch_us_stocks()
    except Exception as e:
        result.errors.append(f"us_stocks: {e}")

    # AAII sentiment
    try:
        result.aaii = _fetch_aaii()
    except Exception as e:
        result.errors.append(f"aaii: {e}")

    # CBOE / VIX fear gauge
    _fetch_cboe_into(result)

    # US → A concept mapping
    _map_us_into(result)

    # Commodities (yfinance)
    try:
        result.commodities = _fetch_commodities()
    except Exception as e:
        result.errors.append(f"commodities: {e}")

    # Commodity → A concept mapping
    _map_commodities_into(result)

    # Korea early-session and overnight warning proxies. This is optional and
    # must never block the rest of the cross-market report.
    try:
        (
            result.korea_quotes,
            result.korea_preopen,
            result.korea_overnight,
        ) = _fetch_korea_signals(trade_date)
    except Exception as e:
        result.errors.append(f"korea: {e}")

    # Macro indicators (FRED + yfinance)
    try:
        result.macros = _fetch_macros()
    except Exception as e:
        result.errors.append(f"macros: {e}")

    return _annotate_freshness(result.to_dict(), trade_date)


def generate_summary(data: dict[str, Any]) -> str:
    """Render a markdown summary for a cross-market snapshot."""
    return _generate_summary(data)


def run_with_chart(trade_date: str | None = None, chart_out: str = "") -> dict[str, Any]:
    """Run cross-market pipeline and optionally generate US overnight chart."""
    data = run(trade_date)
    if (
        chart_out
        and data.get("us_stocks")
        and not isinstance(list(data["us_stocks"].values())[0], str)
    ):
        try:
            from .charts.us_overnight import generate as gen_us

            gen_us(data["us_stocks"], trade_date or "", chart_out)
            data["us_overnight_chart"] = chart_out
        except Exception as e:
            data["errors"].append(f"us_chart: {e}")
    return data
