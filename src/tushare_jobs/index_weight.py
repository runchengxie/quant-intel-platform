"""Compatibility exports for MDP-owned index-weight reference assets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .constants import DEFAULT_INDEX_START_DATE
from .storage import ReferenceAssetUnavailable, load_mdp_asset


@dataclass
class FetchResult:
    label: str
    path: Path
    rows: int


def _index_weight_raw_path(data_dir: Path, index_code: str) -> Path:
    safe_code = index_code.replace(".", "_")
    return data_dir / "index_weight" / f"index_weight_{safe_code}.csv"


def _index_weight_daily_path(data_dir: Path, index_code: str) -> Path:
    safe_code = index_code.replace(".", "_")
    return data_dir / "index_weight_daily" / f"index_weight_daily_{safe_code}.csv"


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def _select_index(dataset: str, index_code: str) -> tuple[pd.DataFrame, Path]:
    frame, source = load_mdp_asset(dataset)
    column = "index_code"
    if column not in frame.columns:
        raise ReferenceAssetUnavailable(f"MDP {dataset} asset lacks {column!r}: {source}")
    selected = frame[frame[column].astype(str) == index_code]
    if selected.empty:
        raise ReferenceAssetUnavailable(
            f"MDP {dataset} asset has no rows for {index_code}: {source}"
        )
    return selected, source


def _try_consume_mdp_index_weight(
    index_code: str,
    *,
    data_dir: Path,
    generate_daily: bool,
) -> list[FetchResult]:
    """Export one index from verified MDP assets into legacy CSV locations."""
    raw, raw_source = _select_index("index_weight", index_code)
    daily: pd.DataFrame | None = None
    daily_source: Path | None = None
    if generate_daily:
        daily, daily_source = _select_index("index_weight_daily", index_code)

    raw_out = _index_weight_raw_path(data_dir, index_code)
    _write_csv(raw, raw_out)
    print(
        f"Consumed MDP index_weight asset ({raw_source}) for {index_code} "
        f"-> {raw_out} ({len(raw)} rows)"
    )
    results = [FetchResult(label=f"index_weight {index_code}", path=raw_out, rows=len(raw))]

    if daily is not None:
        daily_out = _index_weight_daily_path(data_dir, index_code)
        _write_csv(daily, daily_out)
        print(
            f"Consumed MDP index_weight_daily asset ({daily_source}) for {index_code} "
            f"-> {daily_out} ({len(daily)} rows)"
        )
        results.append(
            FetchResult(
                label=f"index_weight_daily {index_code}",
                path=daily_out,
                rows=len(daily),
            )
        )
    return results


def refresh_index_weight(
    pro,
    index_code: str,
    *,
    data_dir: Path,
    default_start: str = DEFAULT_INDEX_START_DATE,
    end_date: str,
    force_full_refresh: bool = False,
    generate_daily: bool = True,
    generate_drift: bool = True,
) -> list[FetchResult]:
    """Export MDP-owned index weights; never refresh them from market-intel."""
    if force_full_refresh:
        raise ReferenceAssetUnavailable(
            "index-weight refresh is owned by market-data-platform; "
            "run `marketdata tushare download-a-share-reference` there"
        )
    return _try_consume_mdp_index_weight(
        index_code,
        data_dir=data_dir,
        generate_daily=generate_daily,
    )


__all__ = ["FetchResult", "refresh_index_weight"]
