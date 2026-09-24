"""Idempotent assembly of a validated daily report artifact."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .facts import build_market_facts
from .macro import fetch_us_macro_facts
from .models import DailyReport, ReportSection
from .serialization import write_json


@dataclass(frozen=True)
class ShadowRunResult:
    artifact_path: str
    source_coverage: float
    degraded_sections: list[str]


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
    if mode == "live":
        fetched_facts, source_status = fetch_us_macro_facts(as_of)
        facts = tuple(fetched_facts)
        source_status.update(
            {
                "quotes": {"quality": "degraded", "reason": "not_connected"},
                "research": {"quality": "degraded", "reason": "not_connected"},
            }
        )
        missing = ["quotes", "research"]
        if source_status["rates"]["quality"] == "lagged":
            missing.append("rates_lag")
        if any(
            value.get("quality") == "degraded"
            for key, value in source_status.items()
            if key not in {"quotes", "research"}
        ):
            missing.append("fred")
        missing_sources = tuple(missing)
        quality = "degraded" if missing_sources else "ok"
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
    market_fact_ids = tuple(fact.id for fact in facts if fact.id.startswith("treasury."))
    macro_fact_ids = tuple(fact.id for fact in facts if fact.id.startswith("macro."))
    if mode != "live":
        market_fact_ids = tuple(fact.id for fact in facts)
    report = DailyReport(
        schema_version="1.0",
        as_of=report_cutoff,
        generated_at=report_cutoff,
        run_id=run_id,
        sections=(
            ReportSection("market", "市场表现", facts=market_fact_ids),
            ReportSection("drivers", "市场驱动因素"),
            ReportSection("macro", "经济数据与美联储动态", facts=macro_fact_ids),
            ReportSection("company_news", "公司新闻"),
            ReportSection("movers", "主要上涨与下跌个股"),
        ),
        facts=facts,
        quality_summary={"status": quality},
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
