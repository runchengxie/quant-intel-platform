"""Public-safe configuration helpers for cross-package project paths."""

from __future__ import annotations

from pathlib import Path

from ops_common.env import resolve_data_platform_root

_UNCONFIGURED_ROOT = Path(".market-intel-external-data-not-configured")


def data_platform_root(*, required: bool = False) -> Path:
    """Return the explicitly configured data root or a non-production sentinel."""

    return resolve_data_platform_root(required=required) or _UNCONFIGURED_ROOT


DATA_PLATFORM_ROOT = data_platform_root()
DATA_ROOT = DATA_PLATFORM_ROOT / "assets" / "tushare" / "a_share"
