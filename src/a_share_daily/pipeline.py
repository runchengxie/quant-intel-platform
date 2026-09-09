"""Morning pipeline orchestrator for the experimental A-share daily report."""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from ops_common.env import resolve_data_platform_root

from . import cross_market as _cross_market
from . import data as D
from .charts import (
    generate_dashboard,
    generate_moneyflow,
    generate_sentiment,
    generate_topic,
    generate_weekly_chart,
    generate_weekly_text,
)
from .charts.theme import save_unavailable_chart
from .cross_market import generate_summary as _gen_cross_summary
from .daily_watch20_validation._common import resolve_watchlist20_root
from .freshness import build_freshness_report
from .topic_summary import TopicSummaryError, load_topic_summary
from .topic_summary_fallback import build_composite_topic_summary
from .weekly_context import write_weekly_context

# ── Config ───────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[2]
HOTSECTOR_INPUT_ENV = "A_SHARE_HOTSECTOR_INPUT"
TOPIC_SUMMARY_INPUT_ENV = "A_SHARE_TOPIC_SUMMARY_INPUT"
OUTPUT_DIR = Path(
    os.environ.get("A_SHARE_OUTPUT_DIR", str(PROJECT_ROOT / "out" / "a_share_daily"))
).expanduser()
FEISHU_CHAT_ID = os.environ.get("A_SHARE_FEISHU_CHAT_ID", "")
EXPECTED_CHART_KEYS = (
    "topic",
    "moneyflow",
    "sentiment",
    "dashboard",
    "weekly_chart",
    "weekly_text",
)
PREMIUM_ENV = "A_SHARE_ENABLE_TUSHARE_PREMIUM"
MONEYFLOW_LATEST_ENV = "A_SHARE_MONEYFLOW_USE_LATEST_AVAILABLE"
DISABLED_REPORT_DATASETS_ENV = "A_SHARE_DISABLED_REPORT_DATASETS"
PREMIUM_DATASETS: tuple[str, ...] = (
    "ths_hot",
    "moneyflow_ths",
    "limit_list_ths",
    "dc_concept",
    "kpl_concept_cons",
    "kpl_list",
    "dc_concept_cons",
)
CORE_DATASETS: tuple[str, ...] = (
    "daily",
    "daily_basic",
    "adj_factor",
    "limit_status",
    "margin",
    "margin_detail",
    "hsgt_top10",
    "index_daily",
    "ths_member",
)


@dataclass
class _ChartState:
    trade_date: str
    results: dict[str, str | None] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)

    def try_chart(self, name: str, fn, *args, **kwargs) -> None:
        try:
            self.results[name] = fn(*args, **kwargs)
        except Exception as exc:
            self.errors[name] = str(exc)[:200]
            self.results[name] = None

    def placeholder(self, name: str, title: str, reason: str, filename: str) -> None:
        self.errors.setdefault(name, reason)
        self.results[name] = save_unavailable_chart(
            title=title,
            trade_date=self.trade_date,
            reason=reason,
            out_path=str(OUTPUT_DIR / filename),
        )


def premium_tushare_enabled() -> bool:
    return os.environ.get(PREMIUM_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def _env_flag(name: str, *, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _split_dataset_env(name: str) -> set[str]:
    raw = os.environ.get(name, "")
    return {item.strip() for item in raw.replace(";", ",").split(",") if item.strip()}


def _load_report_refresh_status(trade_date: str | None) -> dict[str, dict[str, Any]]:
    if not trade_date:
        return {}
    path = (
        resolve_data_platform_root(required=True)
        / "reports"
        / f"a_share_report_dataset_refresh_{trade_date}.json"
    )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    datasets = payload.get("datasets")
    if not isinstance(datasets, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for item in datasets:
        if not isinstance(item, dict):
            continue
        dataset = item.get("dataset")
        if isinstance(dataset, str) and dataset:
            result[dataset] = item
    return result


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        **kwargs,
    )


def _empty_hotsector_reason(data_sources: dict[str, Any] | None = None) -> str:
    if data_sources and any(value is False for value in data_sources.values()):
        return "hotsector 产出 0 只候选，概念数据暂缺"
    return "hotsector 产出 0 只候选"


def step_data_freshness(trade_date: str | None = None) -> dict[str, Any]:
    """Audit data freshness for all core datasets."""
    premium_enabled = premium_tushare_enabled()
    datasets = list(CORE_DATASETS)
    if premium_enabled:
        datasets.extend(PREMIUM_DATASETS)
    disabled_by_config = _split_dataset_env(DISABLED_REPORT_DATASETS_ENV) & set(datasets)
    skipped = set(disabled_by_config)
    skip_reasons = dict.fromkeys(disabled_by_config, "disabled_by_config")
    if not premium_enabled:
        skipped.update(PREMIUM_DATASETS)
        skip_reasons.update(dict.fromkeys(PREMIUM_DATASETS, "premium_disabled"))
    report: dict[str, str | None] = {}
    for ds in datasets:
        latest = D._latest_date(ds, as_of_date=trade_date)
        if ds in ("index_daily", "ths_member") and latest is None:
            # Flat datasets: check file exists
            p = D.DATA_ROOT / ds
            latest = "flat" if p.exists() and list(p.glob("*_latest")) else None
        report[ds] = latest
    return build_freshness_report(
        latest_by_dataset=report,
        target_date=trade_date,
        premium_enabled=premium_enabled,
        skipped_datasets=sorted(skipped),
        refresh_status_by_dataset=_load_report_refresh_status(trade_date),
        skip_reason_by_dataset=skip_reasons,
    )


def step_hotsector(date_str: str) -> dict[str, Any]:
    """Consume an optional owner-produced hotspot candidate artifact."""
    if not premium_tushare_enabled():
        return {
            "ok": False,
            "enabled": False,
            "skipped": True,
            "candidates": 0,
            "universe_json": "",
            "exit_code": 0,
            "reason": "高权限 TuShare 主题数据未启用",
            "data_sources": {},
        }

    raw_input = os.environ.get(HOTSECTOR_INPUT_ENV, "").strip()
    if not raw_input:
        return {
            "ok": False,
            "enabled": True,
            "skipped": True,
            "candidates": 0,
            "universe_json": "",
            "exit_code": 0,
            "reason": "research-workspace 未提供可选热点候选 artifact",
            "data_sources": {},
        }

    universe_json = Path(raw_input).expanduser().resolve()
    if not universe_json.is_file():
        return {
            "ok": False,
            "enabled": True,
            "skipped": True,
            "candidates": 0,
            "universe_json": "",
            "exit_code": 0,
            "reason": f"research-workspace 热点候选 artifact 不存在: {universe_json}",
            "data_sources": {},
        }

    candidates = 0
    reason = ""
    data_sources: dict[str, Any] = {}
    if universe_json.exists():
        try:
            data = json.loads(universe_json.read_text(encoding="utf-8"))
            candidates = len(data.get("candidate_universe", []))
            data_sources = (
                data.get("data_sources", {}) if isinstance(data.get("data_sources"), dict) else {}
            )
            quality_report = data.get("quality_report", {})
            if isinstance(quality_report, dict):
                reason = str(quality_report.get("reason") or "")
        except (json.JSONDecodeError, OSError):
            reason = "candidate_universe.json 解析失败"

    if candidates == 0 and reason == "empty_candidate_universe":
        reason = _empty_hotsector_reason(data_sources)
    if not reason and candidates == 0:
        reason = _empty_hotsector_reason(data_sources)

    return {
        "ok": candidates > 0,
        "candidates": candidates,
        "universe_json": str(universe_json) if universe_json.exists() else "",
        "exit_code": 0,
        "reason": reason,
        "data_sources": data_sources,
    }


def step_topic_summary(date_str: str) -> dict[str, Any]:
    """Consume the topic artifact, or build the report-only DC concept summary."""
    raw_input = os.environ.get(TOPIC_SUMMARY_INPUT_ENV, "").strip()
    topic_summary_json = (
        Path(raw_input).expanduser().resolve()
        if raw_input
        else resolve_watchlist20_root() / "topic_summary.json"
    )
    if not topic_summary_json.is_file():
        try:
            fallback = build_composite_topic_summary(
                date_str,
                concept=D.read_dc_concept(date_str),
                members=D.read_dc_concept_cons(date_str),
                limits=D.read_limit_list(date_str),
                moneyflow=D.read_moneyflow_ths(date_str),
                daily=D.read_daily(date_str),
            )
            fallback_path = OUTPUT_DIR / "topic_summary_fallback.json"
            fallback_path.write_text(
                json.dumps(fallback, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return {
                "ok": True,
                "enabled": True,
                "skipped": False,
                "degraded": fallback["degraded"],
                "topic_count": len(fallback["topics"]),
                "topic_summary_json": str(fallback_path),
                "source": fallback["source"],
                "reason": "",
            }
        except Exception as exc:
            return {
                "ok": False,
                "enabled": True,
                "skipped": True,
                "topic_count": 0,
                "topic_summary_json": "",
                "reason": f"DailyWatch20 topic artifact unavailable; fallback failed: {exc}",
            }
    try:
        # The producer uses the prior close as source_date and the next open
        # session as signal_date.  The pipeline argument is the source/trade
        # date, so validate that boundary without requiring signal_date to be
        # identical to it.
        payload = load_topic_summary(topic_summary_json, expected_source_date=date_str)
    except TopicSummaryError as exc:
        return {
            "ok": False,
            "enabled": True,
            "skipped": False,
            "topic_count": 0,
            "topic_summary_json": str(topic_summary_json),
            "reason": f"topic_summary.json 校验失败: {exc}",
        }
    return {
        "ok": True,
        "enabled": True,
        "skipped": False,
        "topic_count": len(payload["topics"]),
        "topic_summary_json": str(topic_summary_json),
        "source_date": payload["source_date"],
        "signal_date": payload["signal_date"],
        "reason": "",
    }


def _topic_unavailable_reason(universe_path: str) -> str:
    try:
        payload = json.loads(Path(universe_path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return "热点候选池为空或概念数据暂缺，无法生成本交易日主题排名。"
    candidates = payload.get("candidate_universe", [])
    data_sources = payload.get("data_sources", {})
    if isinstance(candidates, list) and len(candidates) == 0:
        if isinstance(data_sources, dict) and any(
            value is False for value in data_sources.values()
        ):
            return "hotsector 产出 0 只候选，概念数据暂缺。无法生成本交易日主题排名。"
        return "hotsector 产出 0 只候选，无法生成本交易日主题排名。"
    return "热点主题列表为空，无法生成本交易日主题排名。"


def _load_daily_chart_inputs(trade_date: str) -> tuple[pd.DataFrame, int]:
    daily = D.read_daily(trade_date)
    limit_up = 0
    with contextlib.suppress(Exception):
        limit_list = D.read_limit_list(trade_date)
        limit_up = int(len(limit_list[limit_list["limit_type"].str.contains("涨停", na=False)]))
    return daily, limit_up


def _daily_chart_failure(exc: Exception) -> dict[str, Any]:
    return {
        "ok": [],
        "degraded": [],
        "failed": list(EXPECTED_CHART_KEYS),
        "paths": dict.fromkeys(EXPECTED_CHART_KEYS),
        "errors": {"daily": str(exc)},
    }


def _run_topic_chart(state: _ChartState, topic_summary_json: str, premium_enabled: bool) -> None:
    if not premium_enabled:
        state.results["topic"] = None
        state.skipped.append("topic")
        return
    if not topic_summary_json or not Path(topic_summary_json).exists():
        state.placeholder(
            "topic",
            "DailyWatch20 热点主题分布",
            (
                "hotsector 未产出 candidate_universe.json，无法生成本交易日主题排名。"
                if not topic_summary_json
                else "DailyWatch20 未产出 topic_summary.json，无法生成本交易日主题分布。"
            ),
            "daily_topic_chart.png",
        )
        return

    state.try_chart(
        "topic", generate_topic, topic_summary_json, str(OUTPUT_DIR / "daily_topic_chart.png")
    )
    if state.results.get("topic") is None:
        state.placeholder(
            "topic",
            "DailyWatch20 热点主题分布",
            (
                _topic_unavailable_reason(topic_summary_json)
                if Path(topic_summary_json).name == "candidate_universe.json"
                else "topic_summary.json 为空或不符合契约，无法生成本交易日主题分布。"
            ),
            "daily_topic_chart.png",
        )


def _run_moneyflow_chart(state: _ChartState, premium_enabled: bool) -> None:
    if not premium_enabled:
        state.results["moneyflow"] = None
        state.skipped.append("moneyflow")
        return
    try:
        moneyflow = D.read_moneyflow_ths(state.trade_date)
        state.try_chart(
            "moneyflow",
            generate_moneyflow,
            moneyflow,
            state.trade_date,
            str(OUTPUT_DIR / "daily_moneyflow_chart.png"),
        )
        if state.results.get("moneyflow") is None:
            state.placeholder(
                "moneyflow",
                "资金流向图",
                "资金流向数据为空，无法生成本交易日主力净流入/流出排名。",
                "daily_moneyflow_chart.png",
            )
    except FileNotFoundError:
        if _env_flag(MONEYFLOW_LATEST_ENV):
            latest = D._latest_date("moneyflow_ths", as_of_date=state.trade_date)
            if latest and latest != state.trade_date:
                try:
                    moneyflow = D.read_moneyflow_ths(latest)
                    state.errors["moneyflow"] = (
                        f"moneyflow_ths {state.trade_date} 暂缺，使用最新可用 {latest}"
                    )
                    state.try_chart(
                        "moneyflow",
                        generate_moneyflow,
                        moneyflow,
                        latest,
                        str(OUTPUT_DIR / "daily_moneyflow_chart.png"),
                    )
                    if state.results.get("moneyflow") is not None:
                        return
                except Exception as exc:
                    state.errors["moneyflow"] = str(exc)[:200]
        state.errors["moneyflow"] = f"数据文件缺失: moneyflow_ths {state.trade_date}"
        state.placeholder(
            "moneyflow",
            "资金流向图",
            "本交易日 moneyflow_ths 分区暂缺，无法生成主力净流入/流出排名。",
            "daily_moneyflow_chart.png",
        )
    except Exception as exc:
        state.errors["moneyflow"] = str(exc)[:200]
        state.placeholder(
            "moneyflow",
            "资金流向图",
            "本交易日 moneyflow_ths 分区暂缺，无法生成主力净流入/流出排名。",
            "daily_moneyflow_chart.png",
        )


def _latest_partition_dates(dataset: str, as_of_date: str | None = None) -> list[str]:
    latest_dirs = list((D.DATA_ROOT / dataset).glob("*_latest"))
    data_dir = D.DATA_ROOT / dataset / latest_dirs[0] / "data"
    dates = sorted(path.name.split("=")[1] for path in data_dir.glob("trade_date=*"))
    if as_of_date:
        dates = [value for value in dates if value <= as_of_date]
    return dates[-5:]


def _recent_margin_data(as_of_date: str | None = None) -> list[dict[str, Any]]:
    margin_data: list[dict[str, Any]] = []
    for day in _latest_partition_dates("margin", as_of_date=as_of_date):
        margin_df = D.read_margin(day)
        if not margin_df.empty:
            margin_data.append({"date": day, "rzye": margin_df["rzye"].sum() / 1e8})
    return margin_data


def _recent_turnover_data(as_of_date: str | None = None) -> list[dict[str, Any]]:
    turnover_data: list[dict[str, Any]] = []
    for day in _latest_partition_dates("daily", as_of_date=as_of_date):
        daily_df = D.read_daily(day)
        turnover_data.append({"date": day, "amount": daily_df["amount"].sum() / 1e5})
    return turnover_data


def _max_board_count(trade_date: str) -> int:
    with contextlib.suppress(Exception):
        step = D.read_limit_step(trade_date)
        return int(step["nums"].max()) if not step.empty else 0
    return 0


def _run_dashboard_chart(state: _ChartState, daily: pd.DataFrame, limit_up: int) -> None:
    try:
        state.try_chart(
            "dashboard",
            generate_dashboard,
            daily,
            limit_up,
            _max_board_count(state.trade_date),
            pd.DataFrame(_recent_margin_data(state.trade_date)),
            pd.DataFrame(_recent_turnover_data(state.trade_date)),
            state.trade_date,
            str(OUTPUT_DIR / "daily_dashboard.png"),
        )
    except Exception as exc:
        state.errors["dashboard"] = str(exc)[:200]


def _load_week_daily(trade_date: str) -> tuple[list[str], dict[str, pd.DataFrame]]:
    from .data import get_week_dates

    week_dates = get_week_dates(trade_date)
    week_daily: dict[str, pd.DataFrame] = {}
    for day in week_dates:
        with contextlib.suppress(Exception):
            week_daily[day] = D.read_daily(day)
    return week_dates, week_daily


def _run_weekly_chart(state: _ChartState) -> tuple[list[str], dict[str, pd.DataFrame]]:
    try:
        week_dates, week_daily = _load_week_daily(state.trade_date)
        if len(week_daily) >= 2:
            state.try_chart(
                "weekly_chart",
                generate_weekly_chart,
                week_daily,
                state.trade_date,
                str(OUTPUT_DIR / "daily_weekly_chart.png"),
            )
        else:
            state.errors["weekly_chart"] = f"only {len(week_daily)} week days"
        return week_dates, week_daily
    except Exception as exc:
        state.errors["weekly_chart"] = str(exc)[:200]
        return [], {}


def _weekly_gold_prices(week_dates: list[str]) -> dict[str, float]:
    week_gold: dict[str, float] = {}
    for day in week_dates:
        snapshot_root = Path(
            os.environ.get("CROSS_MARKET_SNAPSHOT_ROOT", str(PROJECT_ROOT / "data-snapshots"))
        ).expanduser()
        snap_path = snapshot_root / "cross-market" / f"{day[:4]}-{day[4:6]}-{day[6:]}.json"
        with contextlib.suppress(Exception):
            snap = json.loads(snap_path.read_text(encoding="utf-8"))
            gold = snap.get("commodities", {}).get("GC=F", {})
            if isinstance(gold, dict) and "close" in gold:
                week_gold[day] = float(gold["close"])
    return week_gold


def _run_weekly_text(
    state: _ChartState,
    week_dates: list[str],
    week_daily: dict[str, pd.DataFrame],
) -> None:
    try:
        week_limits: dict[str, int] = {}
        week_mf: dict[str, float] = {}
        week_margin: dict[str, float] = {}
        for day in week_dates:
            with contextlib.suppress(Exception):
                limit_list = D.read_limit_list(day)
                week_limits[day] = int(
                    len(limit_list[limit_list["limit_type"].str.contains("涨停", na=False)])
                )
            with contextlib.suppress(Exception):
                moneyflow = D.read_moneyflow_ths(day)
                week_mf[day] = float(moneyflow["net_amount"].sum() / 1e4)
            with contextlib.suppress(Exception):
                margin = D.read_margin(day)
                week_margin[day] = float(margin["rzye"].sum() / 1e8)

        week_gold = _weekly_gold_prices(week_dates)
        text = generate_weekly_text(
            week_daily,
            week_limits,
            week_mf,
            week_margin,
            state.trade_date,
            week_gold=week_gold if week_gold else None,
        )
        weekly_recap_path = OUTPUT_DIR / "weekly_recap.md"
        weekly_recap_metadata_path = OUTPUT_DIR / "weekly_recap.meta.json"
        write_weekly_context(
            weekly_recap_path,
            weekly_recap_metadata_path,
            text,
            target_trade_date=state.trade_date,
            actual_through=max(week_daily) if week_daily else None,
        )
        state.results["weekly_text"] = str(weekly_recap_path)
    except Exception as exc:
        state.errors["weekly_text"] = str(exc)[:200]
        state.results["weekly_text"] = None


def _chart_manifest(state: _ChartState) -> dict[str, Any]:
    ok = [
        key for key, value in state.results.items() if value is not None and key not in state.errors
    ]
    degraded = sorted(
        key for key, value in state.results.items() if value is not None and key in state.errors
    )
    failed = [
        key
        for key in EXPECTED_CHART_KEYS
        if state.results.get(key) is None and key not in state.skipped
    ]
    return {
        "ok": ok,
        "degraded": degraded,
        "failed": failed,
        "skipped": state.skipped,
        "paths": state.results,
        "errors": state.errors,
    }


def step_charts(
    trade_date: str, topic_summary_json: str = "", *, universe_json: str | None = None
) -> dict[str, Any]:
    """Generate all 6 charts. Returns manifest of successes/failures."""
    if universe_json is not None:
        topic_summary_json = universe_json
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    state = _ChartState(trade_date=trade_date)
    try:
        daily, limit_up = _load_daily_chart_inputs(trade_date)
    except Exception as exc:
        return _daily_chart_failure(exc)

    premium_enabled = premium_tushare_enabled()
    _run_topic_chart(state, topic_summary_json, premium_enabled)
    _run_moneyflow_chart(state, premium_enabled)
    state.try_chart(
        "sentiment",
        generate_sentiment,
        daily,
        limit_up,
        trade_date,
        str(OUTPUT_DIR / "daily_sentiment_chart.png"),
    )
    _run_dashboard_chart(state, daily, limit_up)
    week_dates, week_daily = _run_weekly_chart(state)
    _run_weekly_text(state, week_dates, week_daily)
    return _chart_manifest(state)


def run_morning(trade_date: str | None = None) -> dict[str, Any]:
    """Full morning pipeline. Returns manifest dict."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if trade_date is None:
        trade_date = datetime.now().strftime("%Y%m%d")

    date_dash = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"

    # Step 0: Stray data cleanup
    stray_cleaned = 0
    for ds_dir_name in ("ths_hot", "dc_concept", "dc_concept_cons", "kpl_concept_cons"):
        ds_dir = D.DATA_ROOT / ds_dir_name
        stray = ds_dir / "data"
        if stray.is_dir() and list(ds_dir.glob("a_share_all_*_latest")):
            backup_dir = OUTPUT_DIR / "stray_backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            stray.rename(backup_dir / f"{ds_dir_name}_stray_backup_{trade_date}")
            stray_cleaned += 1

    manifest = {
        "pipeline": "morning",
        "report_kind": "morning",
        "date": trade_date,
        "date_dash": date_dash,
        "stray_cleaned": stray_cleaned,
        "freshness": step_data_freshness(trade_date),
        "hotsector": {},
        "topic_summary": {},
        "charts": {},
        "feishu_chat_id": FEISHU_CHAT_ID,
        "instructions": (
            f"Charts and weekly recap are written under {OUTPUT_DIR}. "
            "Delivery is handled outside this experimental package. "
            "Skip failed components and don't block the whole run."
        ),
    }

    # Step 1: DailyWatch20 topic summary
    print("[topic_summary] Running ...", file=sys.stderr)
    topic_summary = step_topic_summary(trade_date)
    manifest["topic_summary"] = topic_summary
    topic_summary_json = topic_summary.get("topic_summary_json", "")

    # Step 2: Charts
    print("[charts] Generating ...", file=sys.stderr)
    manifest["charts"] = step_charts(trade_date, topic_summary_json)

    # Step 3: Cross-market data + US overnight chart
    print("[cross_market] Fetching ...", file=sys.stderr)
    chart_path = str(OUTPUT_DIR / "daily_us_overnight.png")
    manifest["cross_market"] = _cross_market.run_with_chart(trade_date, chart_path)
    if manifest["cross_market"].get("us_overnight_chart"):
        manifest["charts"]["paths"]["us_overnight"] = chart_path
        manifest["charts"]["ok"].append("us_overnight")

    # Step 4: Cross-market summary
    print("[cross_market_summary] Generating ...", file=sys.stderr)
    try:
        summary_md = _gen_cross_summary(manifest["cross_market"])
        summary_path = OUTPUT_DIR / "cross_market_summary.md"
        summary_path.write_text(summary_md, encoding="utf-8")
        manifest["cross_market_summary"] = str(summary_path)
    except Exception as e:
        manifest["cross_market_summary"] = f"error: {e}"

    return manifest


# ── CLI ──────────────────────────────────────────────────────


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Morning pipeline orchestrator")
    parser.add_argument("--date", help="Trade date YYYYMMDD")
    args = parser.parse_args()

    manifest = run_morning(args.date)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
