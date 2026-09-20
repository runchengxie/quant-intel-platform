"""Stable locations for market-intel runtime data.

Source checkouts are disposable.  Persistent reports, receipts and recovery
state therefore belong below the operator supplied ``DATA_PLATFORM_ROOT``.
Individual environment variables remain available for deployments that need a
different layout or are migrating an existing installation.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

from .env import resolve_data_platform_root


def resolve_owner_path(
    owner: str,
    *,
    category: str,
    override_env: str | None = None,
    suffix: Iterable[str] = (),
) -> Path:
    """Resolve a persistent path without writing into the source checkout.

    ``override_env`` is checked first so existing production layouts continue
    to work.  Otherwise the path is derived from ``DATA_PLATFORM_ROOT`` and a
    stable owner name.  A missing root raises before any directory is created.
    """

    if override_env:
        configured = os.environ.get(override_env, "").strip()
        if configured:
            return Path(configured).expanduser()
    root = resolve_data_platform_root(required=True)
    return root / category / owner / Path(*suffix)
