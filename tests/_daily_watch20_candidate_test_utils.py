from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd


def strict_v2_policy_id() -> str:
    return (
        "daily_watch20.ths_hot_positive_close.v2:min_symbols=20:"
        "snapshot_min_symbols=80:close_cutoff_minute=900:"
        "max_snapshot_fallback_minutes=60:batch_gap_seconds=15:"
        "max_component_span_seconds=180:max_missing_ranks=2:"
        "max_snapshot_symbols=100:require_rank_one=true:required_top_ranks=20"
    )


def strict_v3_policy_id() -> str:
    return (
        "daily_watch20.ths_hot_positive_close.v3:min_symbols=20:"
        "snapshot_min_symbols=80:close_cutoff_minute=900:"
        "max_snapshot_fallback_minutes=60:batch_gap_seconds=15:"
        "max_component_span_seconds=180:max_missing_ranks=2:"
        "max_snapshot_symbols=100:require_rank_one=true:required_top_ranks=1"
    )


def write_v2_source(
    root: Path,
    selected: pd.DataFrame,
    *,
    missing_ranks: tuple[int, ...] = (),
) -> Path:
    rank_values = [rank for rank in range(1, 101) if rank not in missing_ranks]
    selected_ranks = [int(value) for value in selected["ths_hot_rank"]]
    selected_symbols = dict(zip(selected_ranks, selected["symbol"].astype(str), strict=True))
    reserved = set(selected_symbols.values())
    generated = (
        symbol for index in range(1000) if (symbol := f"601{index:03d}.SH") not in reserved
    )
    symbols = {rank: selected_symbols.get(rank) or next(generated) for rank in rank_values}
    source = pd.DataFrame(
        {
            "trade_date": ["20260710"] * len(rank_values),
            "data_type": ["热股"] * len(rank_values),
            "platform_market": ["a_share"] * len(rank_values),
            "symbol": [symbols[rank] for rank in rank_values],
            "rank": rank_values,
            "pct_change": [1.0] * len(rank_values),
            "rank_time": ["2026-07-10 16:30:00"] * len(rank_values),
        }
    )
    source_path = root / "ths-hot" / "data" / "trade_date=20260710" / "part.parquet"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source.to_parquet(source_path, index=False)
    return source_path


def v2_candidate_pool(source_path: Path, *, missing_ranks: tuple[int, ...]) -> dict[str, object]:
    snapshot_unique = 100 - len(missing_ranks)
    return {
        "mode": "ths_hot_strict_v2",
        "policy_id": strict_v2_policy_id(),
        "source": "tushare.ths_hot",
        "root": str(source_path.parents[2]),
        "source_date": "20260710",
        "restricted": True,
        "fail_closed": True,
        "positive_change_only": True,
        "min_symbols": 20,
        "snapshot_min_symbols": 80,
        "close_cutoff_minute": 900,
        "max_snapshot_fallback_minutes": 60,
        "snapshot_unique_symbols": snapshot_unique,
        "snapshot_rows": snapshot_unique,
        "pool_symbols": snapshot_unique,
        "eligible_intersection_symbols": snapshot_unique,
        "raw_rows": snapshot_unique,
        "non_positive_rows_removed": 0,
        "files": [
            {
                "path": str(source_path),
                "sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
            }
        ],
        "batch_gap_seconds": 15,
        "max_component_span_seconds": 180,
        "max_missing_ranks": 2,
        "max_snapshot_symbols": 100,
        "require_rank_one": True,
        "required_top_ranks": 20,
        "assembly_path": "minute_sparse_unique" if missing_ranks else "v1_fast_path",
        "deduplicated_snapshot_rows": snapshot_unique,
        "missing_ranks": list(missing_ranks),
        "rank_coverage_status": "degraded" if missing_ranks else "complete",
        "rank_ties": 0,
        "snapshot_minute": "2026-07-10 16:30",
        "latest_observed_minute": "2026-07-10 16:30",
        "skipped_incomplete_snapshots": 0,
        "snapshot_time_min": "2026-07-10 16:30:00",
        "snapshot_time_max": "2026-07-10 16:30:00",
        "component_time_start": "2026-07-10 16:30:00",
        "component_time_end": "2026-07-10 16:30:00",
        "component_span_seconds": 0,
        "duplicate_symbol_rows_removed": 0,
        "out_of_scope_rows_removed": 0,
    }


def v3_candidate_pool(source_path: Path, *, missing_ranks: tuple[int, ...]) -> dict[str, object]:
    candidate = v2_candidate_pool(source_path, missing_ranks=missing_ranks)
    candidate.update(
        {
            "mode": "ths_hot_strict_v3",
            "policy_id": strict_v3_policy_id(),
            "required_top_ranks": 1,
        }
    )
    return candidate


__all__ = [
    "strict_v2_policy_id",
    "strict_v3_policy_id",
    "v2_candidate_pool",
    "v3_candidate_pool",
    "write_v2_source",
]
