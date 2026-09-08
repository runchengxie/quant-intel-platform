"""Internal-only StyleReplica-A80B20-v0 → Feishu bridge.

Thin bridge layer that connects research-workspace's StyleReplica pipeline
to market-intel's Feishu delivery infrastructure.

Does NOT duplicate any factor/portfolio logic — only runs the pipeline
and formats/pushes results to Feishu.

The package is split into:
- ``.render``: pure position formatting (markdown + Feishu card), no I/O.
- ``.delivery``: internal-only delivery guard, lark-cli calls, daily push.

This module re-exports the public surface so existing imports such as
``from style_replica_bridge import push_daily_holdings`` keep working.
"""

# Re-exported at module level because existing tests reach them as
# ``style_replica_bridge.pd`` / ``style_replica_bridge.subprocess``.
import subprocess  # noqa: F401

import pandas as pd  # noqa: F401

from .delivery import (
    DEFAULT_DATA_ROOT,
    INTERNAL_FEISHU_USER_ENV,
    PROJECT_ROOT,
    _resolve_internal_delivery_user,
    _send_lark_image,
    push_daily_holdings,
    send_to_user,
)
from .render import (
    enrich_positions_with_tags,
    format_feishu_card,
    format_holdings_summary,
    load_positions,
)

__all__ = [
    "PROJECT_ROOT",
    "DEFAULT_DATA_ROOT",
    "INTERNAL_FEISHU_USER_ENV",
    "load_positions",
    "enrich_positions_with_tags",
    "format_holdings_summary",
    "format_feishu_card",
    "send_to_user",
    "_send_lark_image",
    "_resolve_internal_delivery_user",
    "push_daily_holdings",
]
