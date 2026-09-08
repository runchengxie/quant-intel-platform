"""Listed-company jobs with read-only MDP reference-asset compatibility exports."""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

from .constants import (
    DATASET_SHARE_FLOAT,
    DATASET_STK_MANAGERS,
    DEDUP_KEYS,
    DEFAULT_FIELDS,
    DEFAULT_SHARE_FLOAT_THRESHOLD,
    ENV_FIELD_OVERRIDES,
)
from .retry import FetchRunner
from .storage import DataStore, ReferenceAssetUnavailable, load_mdp_asset
from .windowing import format_yyyymmdd


@dataclass
class FetchSummary:
    dataset: str
    windows: int = 0
    rows: int = 0
    files: int = 0


class ListedCompanyFetcher:
    def __init__(self, pro: Any, runner: FetchRunner, store: DataStore) -> None:
        self.pro = pro
        self.runner = runner
        self.store = store

    def _resolve_fields(self, dataset: str) -> str | None:
        env_key = ENV_FIELD_OVERRIDES.get(dataset)
        if env_key:
            override = os.getenv(env_key)
            if override:
                return override
        return DEFAULT_FIELDS.get(dataset)

    def _fetch_with_fields(self, label: str, fn, fields: str | None):
        if fields:
            return self.runner.call(label, lambda: fn(fields=fields))
        return self.runner.call(label, fn)

    @staticmethod
    def _dedup(dataset: str, frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame
        keys = DEDUP_KEYS.get(dataset, [])
        subset = [key for key in keys if key in frame.columns]
        if subset:
            return frame.drop_duplicates(subset=subset, keep="last")
        return frame.drop_duplicates()

    def fetch_stock_basic(self, list_status: str) -> FetchSummary:
        """Keep the lightweight report snapshot; MDP owns historical stock basics."""
        fields = self._resolve_fields("stock_basic")
        frame = self._fetch_with_fields(
            f"stock_basic list_status={list_status or 'ALL'}",
            lambda fields=None: self.pro.stock_basic(list_status=list_status, fields=fields),
            fields,
        )
        if frame is None:
            frame = pd.DataFrame()
        frame = self._dedup("stock_basic", frame)
        run_date = date.today()
        self.store.save_raw_snapshot("stock_basic", run_date, frame)
        self.store.save_curated("stock_basic", frame)
        return FetchSummary(dataset="stock_basic", windows=1, rows=len(frame), files=2)

    def fetch_stock_company(self, exchanges: Iterable[str]) -> FetchSummary:
        exchanges = list(exchanges)
        frame, source = load_mdp_asset("stock_company")
        column = "exchange"
        if exchanges and column not in frame.columns:
            raise ReferenceAssetUnavailable(f"MDP stock_company asset lacks {column!r}: {source}")
        selected = frame[frame[column].astype(str).isin(exchanges)] if exchanges else frame
        if selected.empty:
            raise ReferenceAssetUnavailable(
                f"MDP stock_company asset has no rows for exchanges={exchanges}: {source}"
            )
        selected = self._dedup("stock_company", selected)
        run_date = date.today()
        self.store.save_raw_snapshot("stock_company", run_date, selected)
        self.store.save_curated("stock_company", selected)
        print(
            f"Consumed MDP stock_company asset ({source}) "
            f"-> {len(selected)} rows (exchanges={exchanges or 'all'})"
        )
        return FetchSummary(
            dataset="stock_company",
            windows=max(1, len(exchanges)),
            rows=len(selected),
            files=2,
        )

    def fetch_stk_managers(
        self,
        start: date,
        end: date,
        *,
        window: str,
        resume: bool,
        force: bool,
    ) -> FetchSummary:
        return self._consume_mdp_event_asset(DATASET_STK_MANAGERS, start, end)

    def fetch_share_float(
        self,
        start: date,
        end: date,
        *,
        window: str,
        resume: bool,
        force: bool,
        threshold: int = DEFAULT_SHARE_FLOAT_THRESHOLD,
    ) -> FetchSummary:
        return self._consume_mdp_event_asset(DATASET_SHARE_FLOAT, start, end)

    def _consume_mdp_event_asset(
        self,
        dataset: str,
        start: date,
        end: date,
    ) -> FetchSummary:
        frame, source = load_mdp_asset(dataset)
        if "ann_date" not in frame.columns:
            raise ReferenceAssetUnavailable(f"MDP {dataset} asset lacks 'ann_date': {source}")
        start_key = format_yyyymmdd(start)
        end_key = format_yyyymmdd(end)
        dates = frame["ann_date"].astype(str).str.replace("-", "", regex=False)
        selected = frame[(dates >= start_key) & (dates <= end_key)]
        if selected.empty:
            raise ReferenceAssetUnavailable(
                f"MDP {dataset} asset has no rows in {start_key}..{end_key}: {source}"
            )
        selected = self._dedup(dataset, selected)
        self.store.save_raw_window(dataset, start, end, selected)
        self.store.save_curated(dataset, selected)
        print(
            f"Consumed MDP {dataset} asset ({source}) "
            f"for {start_key}..{end_key} -> {len(selected)} rows"
        )
        return FetchSummary(dataset=dataset, windows=1, rows=len(selected), files=2)


__all__ = ["FetchSummary", "ListedCompanyFetcher"]
