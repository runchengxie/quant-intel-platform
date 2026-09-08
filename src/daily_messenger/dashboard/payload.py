"""Build dashboard payloads from local pipeline artifacts.

This module is now a thin composition layer. The implementation lives in the
``payload_*`` submodules; everything below is re-exported so that existing
callers (``web_dashboard``, ``state_panel``) and tests that do
``import ...payload as pmod; pmod.X`` keep working unchanged.

``PROJECT_ROOT`` and the derived path constants stay here on purpose: they are
computed from ``__file__`` and would point to the wrong directory if moved into
a submodule.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

# Re-exports: these names are consumed by external callers (web_dashboard,
# state_panel) and by tests via ``import ...payload as pmod``. The noqa markers
# keep ruff from treating them as unused (they are not referenced inside
# this module itself).
from .payload_aggregations import (  # noqa: F401
    _a_share_snapshot,
    _action_items,
    _chart_rows,
    _etl_source_rows,
    _latest_payload,
    _lead_lag_rows,
    _market_table,
    _neighbor_summary,
    _similar_state_neighbors,
    _theme_cards,
    _volatility_structure,
)
from .payload_coverage import (  # noqa: F401
    ETL_REFERENCE_IDS,
    REFERENCE_SPECS,
    REPLICATION_COST_NOTES,
    REPLICATION_DATA_ROWS,
    REPLICATION_MISSING_ROWS,
    SUPPLY_RECOMMENDATIONS,
    _coverage,
    _known_gap_rows,
    _reference_rows,
    _source_analysis,
    _source_manifest,
    _source_status_from_message,
)
from .payload_helpers import (  # noqa: F401
    CHART_COLUMNS,
    CHART_ROW_LIMIT,
    CHART_SERIES,
    FORWARD_RETURN_COLUMNS,
    NEIGHBOR_LIMIT,
    STATE_COLUMNS,
    USD_CNY_ASSUMPTION,
    JsonDocument,
    PanelDocument,
    _as_list,
    _as_mapping,
    _coerce_row_value,
    _json_default,
    _load_json,
    _number,
    _rounded,
    _theme_valuation_average,
)
from .payload_state import (  # noqa: F401
    DEFAULT_STATE_PANEL_NAME,
    STATE_PANEL_ENV,
    _ensure_state_panel,
    _first_present,
    _latest_panel_row,
    _panel_is_derived,
    _read_state_panel,
    _resolve_state_panel_path,
    _score_label,
    _state_panel_source_label,
    _valuation_label,
)
from .payload_terminal import (  # noqa: F401
    _terminal_payload,
)

PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]
OUT_DIR: Path = PROJECT_ROOT / "out"
SNAPSHOT_DIR: Path = PROJECT_ROOT / "data-snapshots" / "latest"


def build_payload(
    *,
    out_dir: Path = OUT_DIR,
    snapshot_dir: Path = SNAPSHOT_DIR,
    state_panel_path: Path | None = None,
) -> dict[str, object]:
    scores_doc = _load_json(out_dir / "scores.json")
    actions_doc = _load_json(out_dir / "actions.json")
    raw_market_doc = _load_json(out_dir / "raw_market.json")
    raw_events_doc = _load_json(out_dir / "raw_events.json")
    status_doc = _load_json(out_dir / "etl_status.json")
    cross_market_doc = _load_json(snapshot_dir / "cross_market_snapshot.json")
    tushare_doc = _load_json(snapshot_dir / "tushare_snapshot.json")
    panel_doc = _read_state_panel(state_panel_path, out_dir)

    scores = _as_mapping(scores_doc.data)
    raw_market = _as_mapping(raw_market_doc.data)
    raw_events = _as_mapping(raw_events_doc.data)
    cross_market = _as_mapping(cross_market_doc.data)
    actions = _as_mapping(actions_doc.data)
    status = _as_mapping(status_doc.data)
    tushare = _as_mapping(tushare_doc.data)
    panel_doc = _ensure_state_panel(panel_doc, scores, raw_market, cross_market)

    neighbors = _similar_state_neighbors(panel_doc)
    neighbor_summary = _neighbor_summary(neighbors)
    docs = [
        scores_doc,
        actions_doc,
        raw_market_doc,
        raw_events_doc,
        status_doc,
        cross_market_doc,
        tushare_doc,
    ]
    generated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    latest = _latest_payload(scores, raw_market, cross_market, panel_doc)
    coverage = _coverage(
        scores_doc=scores_doc,
        actions_doc=actions_doc,
        raw_market_doc=raw_market_doc,
        status_doc=status_doc,
        cross_market_doc=cross_market_doc,
        tushare_doc=tushare_doc,
        panel_doc=panel_doc,
        neighbors=neighbors,
        neighbor_summary=neighbor_summary,
    )
    terminal = _terminal_payload(
        scores=scores,
        cross_market=cross_market,
        raw_events=raw_events,
        latest=latest,
        panel=panel_doc,
        neighbors=neighbors,
        neighbor_summary=neighbor_summary,
    )
    return {
        "title": "市场全景终端",
        "generatedAt": generated_at,
        "latest": latest,
        "chartRows": _chart_rows(panel_doc),
        "chartSeries": list(CHART_SERIES),
        "neighbors": neighbors,
        "neighborSummary": neighbor_summary,
        "coverage": coverage,
        "terminal": terminal,
        "marketIntel": {
            "themes": _theme_cards(scores),
            "actions": _action_items(actions),
            "etlSources": _etl_source_rows(status),
            "degraded": bool(scores.get("degraded")),
            "date": str(scores.get("date", "")),
        },
        "crossMarket": {
            "date": str(cross_market.get("date", "")),
            "usStocks": _market_table(cross_market, "us_stocks"),
            "commodities": _market_table(cross_market, "commodities"),
            "macros": _market_table(cross_market, "macros"),
            "leadLag": _lead_lag_rows(cross_market),
            "aaii": _as_mapping(cross_market.get("aaii_sentiment")),
            "vix": _as_mapping(cross_market.get("cboe_putcall")),
        },
        "aShare": _a_share_snapshot(tushare),
        "sourceManifest": _source_manifest(docs, panel_doc),
        "sourceAnalysis": _source_analysis(status=status, coverage=coverage, terminal=terminal),
        "notes": [
            "Licensed or proprietary benchmark series are represented only when local data exists.",
            "Optional state-panel metrics are proxies and should be reviewed before use in production.",
            "Missing data is shown as coverage gaps instead of silently substituting remote services.",
        ],
    }
