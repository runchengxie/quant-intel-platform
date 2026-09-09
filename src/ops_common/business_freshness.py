"""Business-date targets and filesystem freshness probes for recovery."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import yaml

SHANGHAI = ZoneInfo("Asia/Shanghai")
CORE_PARTITIONS = (
    "daily/a_share_all_daily_latest",
    "adj_factor/a_share_all_adj_factor_latest",
    "daily_basic/a_share_all_daily_basic_latest",
    "limit_status/a_share_limit_status_latest",
)
REQUIRED_REPORT_DATASETS = frozenset(
    {
        "dc_concept",
        "kpl_concept_cons",
        "limit_list_ths",
    }
)


@dataclass(frozen=True)
class BusinessTargets:
    """Expected source dates at the current local wall-clock time."""

    signal_date: str
    signal_is_open: bool
    previous_open_date: str
    eod_date: str
    minute_date: str
    report_data_date: str


@dataclass(frozen=True)
class FreshnessContext:
    """Filesystem roots used by business-date probes."""

    project_root: Path
    data_root: Path
    open_dates: tuple[str, ...]


@dataclass(frozen=True)
class FreshnessResult:
    """Structured evidence that a stage is or is not at its target date."""

    fresh: bool
    status: str
    target_date: str | None
    actual_date: str | None
    detail: str
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_open_dates(calendar_path: Path, *, through: str) -> tuple[str, ...]:
    """Load A-share open dates through ``YYYYMMDD`` from the local calendar."""

    try:
        frame = pd.read_parquet(calendar_path, columns=["cal_date", "is_open"])
    except Exception as exc:  # noqa: BLE001 - surfaced as a recovery receipt
        raise RuntimeError(f"cannot read trading calendar {calendar_path}: {exc}") from exc
    dates = sorted(
        {
            str(date)
            for date, is_open in zip(frame["cal_date"], frame["is_open"], strict=False)
            if int(is_open) == 1 and str(date) <= through
        }
    )
    if not dates:
        raise RuntimeError(f"trading calendar has no open dates through {through}")
    return tuple(dates)


def build_business_targets(now: datetime, open_dates: Sequence[str]) -> BusinessTargets:
    """Resolve stage-specific latest expected sessions from one trading calendar."""

    local_now = now.astimezone(SHANGHAI)
    signal_date = local_now.strftime("%Y%m%d")
    eligible = sorted({value for value in open_dates if value <= signal_date})
    if not eligible:
        raise RuntimeError(f"no open trading date on or before {signal_date}")
    signal_is_open = signal_date in eligible
    if signal_is_open:
        if len(eligible) < 2:
            raise RuntimeError(f"no previous open trading date before {signal_date}")
        previous = eligible[-2]
    else:
        previous = eligible[-1]
    clock = local_now.timetz().replace(tzinfo=None)

    def target_after(cutoff: time) -> str:
        return signal_date if signal_is_open and clock >= cutoff else previous

    return BusinessTargets(
        signal_date=signal_date,
        signal_is_open=signal_is_open,
        previous_open_date=previous,
        eod_date=target_after(time(17, 30)),
        minute_date=target_after(time(19, 10)),
        report_data_date=target_after(time(20, 30)),
    )


def stage_target(stage_key: str, targets: BusinessTargets) -> str | None:
    """Return the expected business date for a DAG stage."""

    if stage_key in {"daily_market", "current_contract", "evening_report"}:
        return targets.eod_date
    if stage_key == "minute_market":
        return targets.minute_date
    if stage_key == "report_datasets":
        return targets.report_data_date
    if stage_key in {"cross_market", "morning_model", "morning_report"}:
        return targets.previous_open_date if targets.signal_is_open else None
    raise ValueError(f"unknown recovery stage: {stage_key}")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _nonempty_partition(root: Path, target_date: str) -> bool:
    parent = root / "data" if (root / "data").is_dir() else root
    partition = parent / f"trade_date={target_date}"
    try:
        return partition.is_dir() and any(
            path.is_file() and path.stat().st_size > 0 for path in partition.glob("*.parquet")
        )
    except OSError:
        return False


def _latest_partition(root: Path) -> str | None:
    parent = root / "data" if (root / "data").is_dir() else root
    dates = [
        path.name.removeprefix("trade_date=")
        for path in parent.glob("trade_date=????????")
        if path.is_dir()
    ]
    return max(dates) if dates else None


def _daily_market_probe(context: FreshnessContext, target: str) -> FreshnessResult:
    asset_root = context.data_root / "assets/tushare/a_share"
    roots = [asset_root / relative for relative in CORE_PARTITIONS]
    missing = [str(root) for root in roots if not _nonempty_partition(root, target)]
    actual_dates = [value for root in roots if (value := _latest_partition(root))]
    actual = min(actual_dates) if actual_dates else None
    return FreshnessResult(
        fresh=not missing,
        status="fresh" if not missing else "stale",
        target_date=target,
        actual_date=actual,
        detail="all four core TuShare partitions are present"
        if not missing
        else "missing core partitions",
        evidence=tuple(missing or (str(root) for root in roots)),
    )


def _current_contract_probe(context: FreshnessContext, target: str) -> FreshnessResult:
    reports = context.data_root / "reports"
    matches = sorted(reports.glob(f"a_share_current_release_*_{target}.json"))
    payload = _read_json(matches[-1]) if matches else {}
    daily_clean = payload.get("checks", {}).get("daily_clean_manifest", {})
    manifest_path_value = str(daily_clean.get("manifest_path") or "").strip()
    manifest_path = Path(manifest_path_value).expanduser() if manifest_path_value else None
    output_dir = Path(str(daily_clean.get("output_dir") or "")).expanduser()
    data_dir = output_dir / "data" if (output_dir / "data").is_dir() else output_dir
    sentinel = data_dir / "000001.SZ.parquet"
    manifest: Mapping[str, Any] = {}
    if manifest_path is not None:
        try:
            raw_manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            if isinstance(raw_manifest, Mapping):
                manifest = raw_manifest
        except (OSError, yaml.YAMLError):
            manifest = {}
    manifest_query = manifest.get("query", {})
    manifest_output_dir = str(manifest.get("output_dir") or "").strip()
    fresh = all(
        (
            payload.get("status") == "passed",
            daily_clean.get("as_of_date") == target,
            daily_clean.get("status") == "completed",
            manifest_path is not None and manifest_path.is_file(),
            manifest.get("status") == "completed",
            isinstance(manifest_query, Mapping) and manifest_query.get("end_date") == target,
            manifest_path is not None
            and manifest_path.resolve() == (output_dir / "manifest.yml").resolve(),
            manifest_output_dir == str(output_dir),
            sentinel.is_file() and sentinel.stat().st_size > 0,
        )
    )
    latest = sorted(reports.glob("a_share_current_release_*_????????.json"))
    actual = None
    if latest:
        match = re.search(r"_(\d{8})\.json$", latest[-1].name)
        actual = match.group(1) if match else None
    return FreshnessResult(
        fresh=fresh,
        status="fresh" if fresh else "stale",
        target_date=target,
        actual_date=target if fresh else actual,
        detail="current release receipt and daily-clean inputs passed"
        if fresh
        else f"current release receipt or daily-clean sentinel is missing: {sentinel}",
        evidence=tuple(str(path) for path in matches) + (str(sentinel),),
    )


def _report_datasets_probe(context: FreshnessContext, target: str) -> FreshnessResult:
    path = context.data_root / "reports" / f"a_share_report_dataset_refresh_{target}.json"
    payload = _read_json(path)
    raw_rows = payload.get("datasets")
    rows: list[Mapping[str, Any]] = (
        [row for row in raw_rows if isinstance(row, Mapping)] if isinstance(raw_rows, list) else []
    )
    statuses = {str(row.get("dataset")): str(row.get("status")) for row in rows}
    missing = sorted(key for key in REQUIRED_REPORT_DATASETS if statuses.get(key) != "ready")
    fresh = payload.get("trade_date") == target and not missing
    return FreshnessResult(
        fresh=fresh,
        status="fresh" if fresh else "stale",
        target_date=target,
        actual_date=str(payload.get("trade_date") or "") or None,
        detail="required report datasets are ready"
        if fresh
        else "required report datasets are stale",
        evidence=(str(path), *(f"{key}:{statuses.get(key, 'missing')}" for key in missing)),
    )


def _minute_market_probe(context: FreshnessContext, target: str) -> FreshnessResult:
    root = context.data_root / "assets/derived/a_share/minute_1m_tushare"
    fresh = _nonempty_partition(root, target)
    return FreshnessResult(
        fresh=fresh,
        status="fresh" if fresh else "stale",
        target_date=target,
        actual_date=_latest_partition(root),
        detail="operational minute partition is present" if fresh else "minute partition is stale",
        evidence=(str(root / f"trade_date={target}"),),
    )


def _cross_market_probe(context: FreshnessContext, target: str) -> FreshnessResult:
    configured_root = os.environ.get("CROSS_MARKET_SNAPSHOT_ROOT", "").strip()
    snapshot_root = (
        Path(configured_root).expanduser().resolve()
        if configured_root
        else context.project_root / "data-snapshots"
    )
    path = snapshot_root / "latest/cross_market_snapshot.json"
    payload = _read_json(path)
    actual = str(payload.get("date") or "") or None
    fresh = actual == target
    return FreshnessResult(
        fresh=fresh,
        status="fresh" if fresh else "stale",
        target_date=target,
        actual_date=actual,
        detail="cross-market snapshot aligns" if fresh else "cross-market snapshot is stale",
        evidence=(str(path),),
    )


def _morning_model_probe(
    context: FreshnessContext, target: str, signal_date: str
) -> FreshnessResult:
    path = context.data_root / "strategy_outputs/watchlist20/latest/selection_receipt.json"
    payload = _read_json(path)
    fresh = all(
        (
            payload.get("status") == "passed",
            payload.get("quality_status") == "passed",
            payload.get("source_date") == target,
            payload.get("signal_date") == signal_date,
        )
    )
    actual = str(payload.get("source_date") or "") or None
    return FreshnessResult(
        fresh=fresh,
        status="fresh" if fresh else "stale",
        target_date=target,
        actual_date=actual,
        detail="DailyWatch20 model artifact aligns"
        if fresh
        else "DailyWatch20 model artifact is stale",
        evidence=(str(path),),
    )


def _delivery_receipt_ok(path: Path, source_date: str, signal_date: str) -> bool:
    payload = _read_json(path)
    return all(
        (
            payload.get("success") is True,
            payload.get("source_date") == source_date,
            payload.get("signal_date") == signal_date,
        )
    )


def _delivery_state_dir(context: FreshnessContext) -> Path:
    """Resolve delivery receipts from the stable runtime state when configured."""

    configured = os.environ.get("A_SHARE_DELIVERY_STATE_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    return context.project_root / "state/a_share_daily_delivery"


def _strategy_delivery_root(context: FreshnessContext) -> Path:
    """Resolve strategy receipts from stable output before release-local output."""

    configured = os.environ.get("A_SHARE_OUTPUT_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    return context.project_root / "out/a_share_daily"


def _formal_delivery_ok(
    context: FreshnessContext, kind: str, source_date: str, signal_date: str
) -> bool:
    path = _delivery_state_dir(context) / f"{kind}_latest.json"
    payload = _read_json(path)
    generated = str(payload.get("generated_at") or "").replace("-", "")[:8]
    return all(
        (
            payload.get("success") is True,
            payload.get("trade_date") == source_date,
            generated == signal_date,
        )
    )


def report_audit_path(context: FreshnessContext, kind: str, signal_date: str) -> Path:
    configured = os.environ.get("SCHEDULED_RECOVERY_STATE_ROOT", "").strip()
    state_root = (
        Path(configured).expanduser()
        if configured
        else context.project_root / "state/scheduled_recovery"
    )
    return (
        state_root
        / "report_audits"
        / kind
        / f"{signal_date}.json"
    )


def write_report_audit(
    context: FreshnessContext,
    *,
    kind: str,
    source_date: str,
    signal_date: str,
    reason: str,
) -> Path:
    """Record that an expired report was generated without delivery."""

    path = report_audit_path(context, kind, signal_date)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "scheduled_report_audit.v1",
        "kind": kind,
        "source_date": source_date,
        "signal_date": signal_date,
        "status": "passed",
        "delivery_attempted": False,
        "reason": reason,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def _report_probe(
    context: FreshnessContext,
    *,
    kind: str,
    source_date: str,
    signal_date: str,
    mode: str,
) -> FreshnessResult:
    if mode == "audit_only":
        path = report_audit_path(context, kind, signal_date)
        payload = _read_json(path)
        fresh = all(
            (
                payload.get("status") == "passed",
                payload.get("delivery_attempted") is False,
                payload.get("source_date") == source_date,
                payload.get("signal_date") == signal_date,
            )
        )
        return FreshnessResult(
            fresh=fresh,
            status="audit_ready" if fresh else "audit_missing",
            target_date=source_date,
            actual_date=str(payload.get("source_date") or "") or None,
            detail="expired report audit is present"
            if fresh
            else "expired report audit is missing",
            evidence=(str(path),),
        )
    formal_ok = _formal_delivery_ok(context, kind, source_date, signal_date)
    delivery_state_dir = _delivery_state_dir(context)
    evidence = [str(delivery_state_dir / f"{kind}_latest.json")]
    if kind == "morning":
        output_root = _strategy_delivery_root(context)
        daily = (
            output_root
            / "daily_watch20"
            / signal_date
            / "delivery_receipt.json"
        )
        d11 = (
            output_root
            / "d11_h5_shadow"
            / signal_date
            / "delivery_receipt.json"
        )
        formal_ok = formal_ok and _delivery_receipt_ok(daily, source_date, signal_date)
        formal_ok = formal_ok and _delivery_receipt_ok(d11, source_date, signal_date)
        evidence.extend((str(daily), str(d11)))
    return FreshnessResult(
        fresh=formal_ok,
        status="fresh" if formal_ok else "stale",
        target_date=source_date,
        actual_date=source_date if formal_ok else None,
        detail=f"{kind} delivery receipts align"
        if formal_ok
        else f"{kind} delivery receipts are stale",
        evidence=tuple(evidence),
    )


def probe_stage(
    context: FreshnessContext,
    *,
    stage_key: str,
    target_date: str,
    signal_date: str,
    report_mode: str = "deliver",
) -> FreshnessResult:
    """Probe one stage using its production partition or receipt contract."""

    if stage_key == "daily_market":
        return _daily_market_probe(context, target_date)
    if stage_key == "minute_market":
        return _minute_market_probe(context, target_date)
    if stage_key == "current_contract":
        return _current_contract_probe(context, target_date)
    if stage_key == "report_datasets":
        return _report_datasets_probe(context, target_date)
    if stage_key == "cross_market":
        return _cross_market_probe(context, target_date)
    if stage_key == "morning_model":
        return _morning_model_probe(context, target_date, signal_date)
    if stage_key == "morning_report":
        return _report_probe(
            context,
            kind="morning",
            source_date=target_date,
            signal_date=signal_date,
            mode=report_mode,
        )
    if stage_key == "evening_report":
        return _report_probe(
            context,
            kind="evening",
            source_date=target_date,
            signal_date=target_date,
            mode=report_mode,
        )
    raise ValueError(f"unknown recovery stage: {stage_key}")


def missing_daily_sessions(context: FreshnessContext, target_date: str) -> tuple[str, ...]:
    """Return missing tail sessions across all four core daily mirrors."""

    asset_root = context.data_root / "assets/tushare/a_share"
    roots = [asset_root / relative for relative in CORE_PARTITIONS]
    present_by_root = [
        {
            path.name.removeprefix("trade_date=")
            for path in (root / "data").glob("trade_date=????????")
            if path.is_dir()
        }
        for root in roots
    ]
    common = set.intersection(*present_by_root) if all(present_by_root) else set()
    latest_common = max((value for value in common if value <= target_date), default=None)
    if latest_common is None:
        return (target_date,)
    return tuple(
        value
        for value in context.open_dates
        if latest_common < value <= target_date
        and any(value not in present for present in present_by_root)
    )
