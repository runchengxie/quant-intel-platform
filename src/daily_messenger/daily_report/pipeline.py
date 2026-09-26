"""Idempotent assembly of a validated daily report artifact."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .btc_spot import fetch_btc_spot_facts
from .cross_asset import fetch_cross_asset_facts
from .facts import build_market_facts
from .index_quotes import fetch_index_facts
from .macro import fetch_us_macro_facts
from .models import DailyReport, MarketFact, ReportSection
from .reviewed_research import ReviewedResearch, load_reviewed_research
from .serialization import write_json


@dataclass(frozen=True)
class ShadowRunResult:
    artifact_path: str
    source_coverage: float
    degraded_sections: list[str]


@dataclass(frozen=True)
class LiveInputs:
    facts: tuple[MarketFact, ...]
    source_status: dict[str, dict[str, Any]]
    missing_sources: tuple[str, ...]
    quality: str
    reviewed: ReviewedResearch | None


def _fixture_payloads(as_of: datetime) -> dict[str, Any]:
    return {
        "treasury": {
            "2Y": {"change_bp": 8.0},
            "5Y": {"change_bp": 6.0},
            "10Y": {"change_bp": 4.0},
        },
        "quotes": {
            "SPX": {"value": 0.16, "previous": 0.0},
            "WTI": {"value": -1.6, "previous": 0.0},
        },
        "as_of": as_of.isoformat(),
    }


def _live_inputs(as_of: datetime, run_date: str, config: dict[str, Any]) -> LiveInputs:
    fetched_facts, macro_status = fetch_us_macro_facts(as_of)
    source_status: dict[str, dict[str, Any]] = {
        key: dict(value) for key, value in macro_status.items()
    }
    cross_asset_facts, missing_contracts = fetch_cross_asset_facts(
        datetime.fromisoformat(run_date).date()
    )
    btc_spot_facts, btc_spot_status = fetch_btc_spot_facts(datetime.fromisoformat(run_date).date())
    draft_path = config.get("reviewed_draft")
    decision_path = config.get("reviewed_decisions")
    if bool(draft_path) != bool(decision_path):
        raise ValueError("reviewed draft and decisions must be provided together")
    reviewed = (
        load_reviewed_research(
            Path(draft_path),
            Path(decision_path),
            market_date=run_date,
            as_of=as_of,
        )
        if draft_path and decision_path
        else None
    )
    index_facts, missing_indices = (
        ([], ())
        if reviewed and reviewed.facts
        else fetch_index_facts(datetime.fromisoformat(run_date).date())
    )
    facts = (
        tuple(fetched_facts)
        + tuple(index_facts)
        + tuple(cross_asset_facts)
        + tuple(btc_spot_facts)
        + (reviewed.facts if reviewed else ())
    )
    source_status["cross_asset"] = {
        "quality": "degraded" if missing_contracts else "ok",
        "reason": "one_or_more_contracts_unavailable"
        if missing_contracts
        else "all_contracts_fresh",
        "missing_contracts": missing_contracts,
    }
    source_status["btc_spot"] = {
        "quality": "ok" if btc_spot_facts else "degraded",
        "reason": btc_spot_status,
    }
    source_status.update(
        {
            "quotes": {
                "quality": "reviewed"
                if reviewed and reviewed.facts
                else "degraded"
                if missing_indices
                else "ok",
                "reason": "source_audited"
                if reviewed and reviewed.facts
                else "one_or_more_indices_unavailable"
                if missing_indices
                else "all_indices_fresh",
            },
            "research": {
                "quality": "reviewed" if reviewed and reviewed.claims else "degraded",
                "reason": "source_audited" if reviewed and reviewed.claims else "not_connected",
            },
        }
    )
    missing = [
        name for name in ("quotes", "research") if source_status[name]["quality"] == "degraded"
    ]
    if missing_contracts:
        missing.append("cross_asset")
    if source_status["rates"]["quality"] == "lagged":
        missing.append("rates_lag")
    if (
        source_status["macro"]["quality"] == "degraded"
        or source_status["rates"]["quality"] == "degraded"
    ):
        missing.append("fred")
    return LiveInputs(
        facts=facts,
        source_status=source_status,
        missing_sources=tuple(missing),
        quality="degraded" if missing else "ok",
        reviewed=reviewed,
    )


def _live_revision(report_cutoff: datetime, run_date: date) -> str | None:
    market_cutoff = report_cutoff.astimezone(ZoneInfo("America/New_York"))
    if market_cutoff.date() == run_date:
        return None
    if market_cutoff.date() == run_date + timedelta(days=1) and market_cutoff.time() < time(9, 30):
        return "next_morning_rechecked"
    return "historical_backfill"


def _sections_for(
    facts: tuple[MarketFact, ...], reviewed: ReviewedResearch | None, *, live: bool
) -> tuple[ReportSection, ...]:
    market_ids = tuple(fact.id for fact in facts if fact.id.startswith(("treasury.", "index.")))
    if not live:
        market_ids = tuple(fact.id for fact in facts)
    cross_asset_ids = tuple(fact.id for fact in facts if fact.id.startswith("cross_asset."))
    macro_ids = tuple(fact.id for fact in facts if fact.id.startswith("macro."))
    return (
        ReportSection(
            "market",
            "市场表现",
            facts=market_ids,
            claims=reviewed.sections["market"] if reviewed else (),
        ),
        ReportSection("cross_asset", "跨资产行情", facts=cross_asset_ids),
        ReportSection(
            "drivers", "市场驱动因素", claims=reviewed.sections["drivers"] if reviewed else ()
        ),
        ReportSection(
            "macro",
            "经济数据与美联储动态",
            facts=macro_ids,
            claims=reviewed.sections["macro"] if reviewed else (),
        ),
        ReportSection(
            "company_news",
            "公司新闻",
            claims=reviewed.sections["company_news"] if reviewed else (),
        ),
        ReportSection(
            "movers",
            "主要上涨与下跌个股",
            claims=(reviewed.sections["gainers"] + reviewed.sections["losers"]) if reviewed else (),
        ),
    )


def run_daily_report(
    as_of: datetime,
    output_dir: str | Path,
    *,
    provider_config: dict[str, Any] | None = None,
) -> DailyReport:
    config = provider_config or {"mode": "live"}
    mode = config.get("mode", "live")
    if mode not in {"live", "fixture", "fail"}:
        raise ValueError(f"unsupported daily report mode: {mode}")
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    run_date = (
        as_of.astimezone(ZoneInfo("America/New_York")).date()
        if mode == "live"
        else as_of.astimezone(UTC).date()
    )
    run_id = f"daily-{run_date.isoformat()}"
    reviewed = None
    if mode == "live":
        live = _live_inputs(as_of, run_date.isoformat(), config)
        facts, source_status = live.facts, live.source_status
        missing_sources, quality, reviewed = live.missing_sources, live.quality, live.reviewed
    else:
        facts = tuple(
            replace(fact, retrieved_at=as_of)
            for fact in build_market_facts(_fixture_payloads(as_of), as_of=as_of)
        )
        source_status = {
            "facts": {"quality": "fixture"},
            "research": {"quality": "degraded" if mode == "fail" else "fixture"},
        }
        missing_sources = ("research",) if mode == "fail" else ()
        quality = "fixture"
    report_cutoff = datetime.now(UTC) if mode == "live" else as_of
    quality_summary = {"status": quality}
    if reviewed:
        quality_summary["reviewed_source_cutoff"] = as_of.isoformat()
    if mode == "live":
        revision = (
            "historical_backfill"
            if config.get("backfill")
            else _live_revision(report_cutoff, run_date)
        )
        if revision:
            quality_summary["revision"] = revision
    report = DailyReport(
        schema_version="1.0",
        as_of=report_cutoff,
        generated_at=report_cutoff,
        run_id=run_id,
        sections=_sections_for(facts, reviewed, live=mode == "live"),
        facts=facts,
        events=reviewed.events if reviewed else (),
        claims=reviewed.claims if reviewed else (),
        quality_summary=quality_summary,
        source_status=source_status,
        missing_sources=missing_sources,
    )
    base = report.to_dict()
    base["content_hash"] = None
    digest = hashlib.sha256(
        json.dumps(base, default=str, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    report = replace(report, content_hash=digest)
    write_json(output_path / "daily_report.json", report)
    return report


def shadow_run(
    date: str,
    output_dir: str | Path,
    *,
    provider_config: dict[str, Any] | None = None,
) -> ShadowRunResult:
    cutoff = datetime.fromisoformat(date).replace(hour=1, tzinfo=UTC)
    report = run_daily_report(cutoff, output_dir, provider_config=provider_config)
    degraded = [
        name for name, status in report.source_status.items() if status.get("quality") == "degraded"
    ]
    return ShadowRunResult(
        artifact_path=str(Path(output_dir) / "daily_report.json"),
        source_coverage=1.0 if report.facts else 0.0,
        degraded_sections=degraded,
    )
