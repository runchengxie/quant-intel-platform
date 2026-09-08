"""Render the published DailyWatch20 selection artifact.

This module is deliberately a consumer. It validates the producer receipt and
formats the already-selected 4+16 watchlist; it does not rank or select stocks.

The validation helpers previously defined inline have been physically moved to
``daily_watch20_validation`` (a pure refactor). Callers that need them import
directly from that subpackage; this module no longer re-exports its private
symbols.
"""

from __future__ import annotations

import html
import math
import os
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pandas as pd

from ops_common.env import resolve_data_platform_root

from .daily_watch20_candidate_pool import THS_HOT_STRICT_V2, THS_HOT_STRICT_V3
from .daily_watch20_freshness_contract import (
    DailyWatch20FreshnessError,
    validate_sparse_input_freshness,
)
from .daily_watch20_validation._common import (
    DATA_FILENAMES,
    DEFAULT_WATCHLIST20_ROOT,
    RECEIPT_FILENAMES,
    WATCHLIST_SCHEMA_V2,
    DailyWatch20ValidationError,
    _date_key,
    _load_json_mapping,
    _normalize_watchlist_frame,
    _parse_bool,
    _read_watchlist_frame,
    _resolve_existing,
    resolve_watchlist20_root,
)
from .daily_watch20_validation.candidate_contract import (
    _validate_candidate_pool_contract,
)
from .daily_watch20_validation.frame_contract import (
    _validate_artifact_inventory,
    _validate_companion_json,
    _validate_frame_contract,
    _validate_minute_receipt,
)
from .daily_watch20_validation.receipt_contract import (
    _validate_receipt_contract,
    _validate_receipt_totals,
)

_PALETTE = (
    "#1557ff",
    "#4778f2",
    "#7696ed",
    "#9eb2e6",
    "#becce3",
    "#d5deea",
    "#e6ebf1",
    "#f0f2f4",
)


@dataclass(frozen=True)
class DailyWatch20Artifact:
    root: Path
    data_path: Path
    receipt_path: Path
    frame: pd.DataFrame
    receipt: dict[str, Any]
    source_date: str
    signal_date: str
    companion_json_path: Path | None = None

    @property
    def a_frame(self) -> pd.DataFrame:
        return self.frame.loc[self.frame["sleeve"] == "A"].copy()

    @property
    def b_frame(self) -> pd.DataFrame:
        return self.frame.loc[self.frame["sleeve"] == "B"].copy()


@dataclass(frozen=True)
class DailyWatch20RenderResult:
    artifact: DailyWatch20Artifact
    html_path: Path
    png_path: Path


def _resolve_trade_calendar_path(receipt: Mapping[str, Any], explicit: str | Path | None) -> Path:
    if explicit is not None:
        path = Path(explicit).expanduser().resolve()
    else:
        env_path = os.environ.get("A_SHARE_TRADE_CAL_FILE")
        inputs = receipt.get("inputs")
        receipt_path = inputs.get("trade_cal") if isinstance(inputs, Mapping) else None
        platform_root = resolve_data_platform_root(required=True)
        path = (
            Path(
                env_path
                or str(receipt_path or "")
                or platform_root
                / "assets/tushare/a_share/trade_cal/a_share_trade_cal_latest.parquet"
            )
            .expanduser()
            .resolve()
        )
    if not path.is_file():
        raise DailyWatch20ValidationError(
            f"trade calendar is required for minute freshness: {path}"
        )
    return path


def _validate_production_input_freshness(
    receipt: Mapping[str, Any],
    *,
    schema_version: str,
    expected_mode: str | None,
    receipt_mode: object,
    source_date: str,
    signal_date: str,
) -> None:
    sparse_modes = {THS_HOT_STRICT_V2, THS_HOT_STRICT_V3}
    expected_sparse = expected_mode in sparse_modes
    policy = receipt.get("strategy_policy")
    safety = policy.get("safety") if isinstance(policy, Mapping) else None
    production_sparse = (
        schema_version == WATCHLIST_SCHEMA_V2
        and isinstance(safety, Mapping)
        and safety.get("publication_tier") == "production"
        and receipt_mode in sparse_modes
    )
    if expected_sparse and (
        receipt.get("publication_tier") != "production" or not production_sparse
    ):
        raise DailyWatch20ValidationError(
            "client sparse strict artifact must have publication_tier=production"
        )
    if not (expected_sparse or production_sparse):
        return
    freshness_mode = str(expected_mode or receipt_mode or "")
    if freshness_mode not in sparse_modes:
        raise DailyWatch20ValidationError(
            "production artifact must use a sparse strict candidate pool"
        )
    try:
        validate_sparse_input_freshness(
            receipt,
            source_date=source_date,
            signal_date=signal_date,
            expected_mode=freshness_mode,
        )
    except DailyWatch20FreshnessError as exc:
        raise DailyWatch20ValidationError(str(exc)) from exc


def load_daily_watch20(
    root: str | Path | None = None,
    *,
    expected_source_date: str | None = None,
    expected_signal_date: str | None = None,
    trade_calendar_path: str | Path | None = None,
    expected_minute_lag_trade_days: int = 0,
    expected_candidate_pool_mode: str | None = None,
) -> DailyWatch20Artifact:
    resolved_root = resolve_watchlist20_root(root)
    if not resolved_root.is_dir():
        raise DailyWatch20ValidationError(f"watchlist root does not exist: {resolved_root}")
    receipt_path = _resolve_existing(resolved_root, RECEIPT_FILENAMES, label="selection receipt")
    receipt = _load_json_mapping(receipt_path, label="selection receipt")
    source_date, signal_date, schema_version = _validate_receipt_contract(receipt)
    candidate_pool = receipt.get("candidate_pool")
    receipt_candidate_mode = (
        candidate_pool.get("mode") if isinstance(candidate_pool, Mapping) else None
    )
    sparse_modes = {THS_HOT_STRICT_V2, THS_HOT_STRICT_V3}
    expected_sparse = expected_candidate_pool_mode in sparse_modes
    if (
        expected_sparse or receipt_candidate_mode in sparse_modes
    ) and schema_version != WATCHLIST_SCHEMA_V2:
        raise DailyWatch20ValidationError(
            "sparse strict candidate pool requires daily_watch20.selection.v2"
        )
    _validate_receipt_totals(receipt)
    calendar_path = _resolve_trade_calendar_path(receipt, trade_calendar_path)
    _validate_minute_receipt(
        receipt,
        source_date=source_date,
        trade_calendar_path=calendar_path,
        expected_lag_trade_days=expected_minute_lag_trade_days,
    )
    _validate_artifact_inventory(resolved_root, receipt)
    if expected_source_date and source_date != _date_key(
        expected_source_date, field="expected_source_date"
    ):
        raise DailyWatch20ValidationError(
            f"stale artifact: source_date={source_date}, expected={_date_key(expected_source_date, field='expected_source_date')}"
        )
    if expected_signal_date and signal_date != _date_key(
        expected_signal_date, field="expected_signal_date"
    ):
        raise DailyWatch20ValidationError(
            f"signal_date={signal_date} does not match expected {_date_key(expected_signal_date, field='expected_signal_date')}"
        )
    data_path = _resolve_existing(resolved_root, DATA_FILENAMES, label="watchlist data")
    frame = _normalize_watchlist_frame(
        _read_watchlist_frame(data_path), schema_version=schema_version
    )
    _validate_frame_contract(
        frame,
        receipt,
        source_date=source_date,
        signal_date=signal_date,
        schema_version=schema_version,
    )
    _validate_production_input_freshness(
        receipt,
        schema_version=schema_version,
        expected_mode=expected_candidate_pool_mode,
        receipt_mode=receipt_candidate_mode,
        source_date=source_date,
        signal_date=signal_date,
    )
    _validate_candidate_pool_contract(
        receipt,
        frame,
        source_date=source_date,
        expected_mode=expected_candidate_pool_mode,
    )
    companion_json = resolved_root / "watchlist_20.json"
    if data_path.suffix.lower() == ".csv" and companion_json.is_file():
        _validate_companion_json(frame, companion_json, schema_version=schema_version)
    else:
        companion_json = None
    return DailyWatch20Artifact(
        root=resolved_root,
        data_path=data_path,
        receipt_path=receipt_path,
        frame=frame,
        receipt=receipt,
        source_date=source_date,
        signal_date=signal_date,
        companion_json_path=companion_json,
    )


def _group_weights(frame: pd.DataFrame, column: str) -> pd.Series:
    labels = frame[column].replace("", "未分类")
    grouped = frame.assign(_label=labels).groupby("_label")["tracking_weight"].sum()
    return cast(pd.Series, grouped.sort_values(ascending=False))


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], frame.to_dict(orient="records"))


def _split_tokens(value: Any) -> list[str]:
    return [
        token.strip() for token in re.split(r"[|；;、,，\n]+", str(value or "")) if token.strip()
    ]


def _top_text_items(frame: pd.DataFrame, column: str, *, limit: int = 6) -> list[str]:
    counts: Counter[str] = Counter()
    for value in frame[column]:
        counts.update(list(dict.fromkeys(_split_tokens(value))))
    return [item for item, _count in counts.most_common(limit)]


def _top_with_other(weights: pd.Series, *, limit: int) -> pd.Series:
    if len(weights) <= limit:
        return weights
    head = weights.iloc[:limit].copy()
    head.loc["其他"] = float(weights.iloc[limit:].sum())
    return head


def _date_dash(value: str) -> str:
    return f"{value[:4]}-{value[4:6]}-{value[6:]}"


def _regime_summary(receipt: Mapping[str, Any]) -> str:
    regime = receipt.get("regime") or receipt.get("regime_summary")
    if isinstance(regime, Mapping):
        parts = [
            str(regime.get(key) or "").strip()
            for key in ("label", "name", "state", "summary", "description")
        ]
        unique = list(dict.fromkeys(part for part in parts if part))
        return " · ".join(unique) if unique else "未提供 regime 摘要"
    text = str(regime or "").strip()
    return text or "未提供 regime 摘要"


def _minute_summary(receipt: Mapping[str, Any]) -> str:
    minute = receipt.get("minute_features")
    if not isinstance(minute, Mapping) or not _parse_bool(minute.get("enabled")):
        return "分钟特征：未启用"
    as_of = str(minute.get("as_of") or "n/a")
    lag = str(minute.get("lag_trade_days", "n/a"))
    return f"分钟特征：as-of {as_of}，滞后 {lag} 个交易日"


def _score_text(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    return f"{number:.3f}" if math.isfinite(number) else "-"


def _html_table(frame: pd.DataFrame) -> str:
    rows: list[str] = []
    for row in _records(frame):
        new_badge = '<span class="badge new">NEW</span>' if bool(row["is_new"]) else ""
        confirm_badge = (
            '<span class="badge confirm">双确认</span>' if bool(row["dual_confirmed"]) else ""
        )
        rows.append(
            "<tr>"
            f"<td>{int(row['rank'])}</td>"
            f"<td><strong>{html.escape(str(row['name']))}</strong><small>{html.escape(str(row['symbol']))}</small></td>"
            f"<td>{html.escape(str(row['industry'] or '未分类'))}</td>"
            f"<td>{html.escape(str(row['theme'] or '未分类'))}</td>"
            f"<td>{float(row['tracking_weight']):.1%}</td>"
            f"<td>{_score_text(row['final_score'])}</td>"
            f"<td>{new_badge}{confirm_badge}</td>"
            "</tr>"
        )
    return "".join(rows)


def _donut_style(weights: pd.Series) -> str:
    start = 0.0
    stops: list[str] = []
    for index, value in enumerate(weights):
        end = start + float(value) * 100.0
        stops.append(f"{_PALETTE[index % len(_PALETTE)]} {start:.3f}% {end:.3f}%")
        start = end
    return "conic-gradient(" + ",".join(stops) + ")"


def _theme_legend(weights: pd.Series) -> str:
    items = []
    for index, (label, value) in enumerate(weights.items()):
        color = _PALETTE[index % len(_PALETTE)]
        items.append(
            '<div class="legend-item">'
            f'<i style="background:{color}"></i><span>{html.escape(str(label))}</span>'
            f"<b>{float(value):.1%}</b></div>"
        )
    return "".join(items)


def _industry_bars(weights: pd.Series) -> str:
    maximum = float(weights.max()) if not weights.empty else 1.0
    rows = []
    for index, (label, value) in enumerate(weights.items()):
        width = float(value) / maximum * 100.0 if maximum else 0.0
        rows.append(
            '<div class="bar-row">'
            f"<span>{html.escape(str(label))}</span>"
            f'<div class="bar-track"><i style="width:{width:.1f}%;background:{_PALETTE[index % len(_PALETTE)]}"></i></div>'
            f"<b>{float(value):.1%}</b></div>"
        )
    return "".join(rows)


def _build_internal_html_document(
    *,
    artifact: DailyWatch20Artifact,
    industry: pd.Series,
    themes: pd.Series,
    a_weight: float,
    b_weight: float,
    drivers: list[str],
    risks: list[str],
    model: str,
    feature_set: str,
) -> str:
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>今日20只重点关注 {_date_dash(artifact.signal_date)}</title>
<style>
:root{{--bg:#f7f4ec;--wash:#edf0fa;--panel:rgba(255,255,255,.52);--panel2:rgba(237,240,250,.64);--line:#cdd0cf;--gridline:rgba(205,208,207,.34);--text:#111820;--muted:#707985;--a:#2c8a64;--b:#1557ff;--warn:#a86f00}}
*{{box-sizing:border-box}}
body{{margin:0;background-color:var(--bg);background-image:
linear-gradient(90deg,var(--gridline) 1px,transparent 1px),
linear-gradient(var(--gridline) 1px,transparent 1px),
linear-gradient(105deg,var(--bg),var(--wash));background-size:40px 40px,
40px 40px,100% 100%;color:var(--text);font:14px/1.55 Inter,
"Noto Sans CJK SC","Microsoft YaHei",sans-serif}}
.wrap{{max-width:1280px;margin:auto;padding:36px 30px}}
header{{padding-bottom:20px;border-bottom:1px solid var(--line)}}
.kicker{{color:var(--b);font-size:12px;font-weight:800;letter-spacing:.04em}}
h1{{font:800 35px/1.2 "Source Han Serif SC","Noto Serif CJK SC","Songti SC",serif;margin:10px 0 6px}}
h2{{font-size:18px;margin:0 0 14px}}p{{margin:0}}.meta{{color:var(--muted)}}
.status{{display:inline-flex;margin-top:12px;padding:4px 0;color:var(--b);font-size:12px;font-weight:800}}
.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:22px;margin:22px 0}}
.card,.panel{{background:var(--panel);border-top:2px solid var(--line)}}
.card{{padding:14px 4px}}.card small{{display:block;color:var(--muted)}}
.card strong{{font-size:23px}}.a{{color:var(--a)}}.b{{color:var(--b)}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-bottom:18px}}
.panel{{padding:18px}}
.bar-row{{display:grid;grid-template-columns:110px 1fr 48px;gap:10px;
align-items:center;margin:10px 0}}
.bar-row span{{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.bar-row b{{text-align:right}}.bar-track{{height:9px;background:#e4e7e8}}
.bar-track i{{display:block;height:100%}}
.theme-box{{display:grid;grid-template-columns:190px 1fr;gap:24px;align-items:center}}
.donut{{width:180px;height:180px;border-radius:50%;position:relative}}
.donut:after{{content:'20';position:absolute;inset:44px;border-radius:50%;
background:#f8f7f2;display:grid;place-items:center;font-size:30px;font-weight:700}}
.legend-item{{display:grid;grid-template-columns:10px 1fr 46px;gap:8px;
align-items:center;margin:7px 0}}
.legend-item i{{width:9px;height:9px;border-radius:50%}}
.legend-item b{{text-align:right}}
.table-panel{{margin-bottom:18px;padding:0;overflow:hidden}}
.table-head{{display:flex;justify-content:space-between;padding:16px 18px;
border-bottom:1px solid var(--line)}}
table{{width:100%;border-collapse:collapse}}
th,td{{padding:10px 12px;border-bottom:1px solid var(--line);text-align:left}}
th{{color:var(--muted);font-size:12px;background:var(--panel2)}}
tbody tr:nth-child(even){{background:rgba(255,255,255,.26)}}
td small{{display:block;color:var(--muted)}}
.badge{{display:inline-block;padding:2px 5px;margin:2px;border:1px solid var(--line);
font-size:10px}}.new{{color:var(--b);font-weight:800}}.confirm{{color:var(--a)}}
.notes{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:18px}}
ul{{padding-left:18px;margin:0}}li{{margin:7px 0}}
footer{{color:var(--muted);margin-top:18px;padding-top:12px;
border-top:1px solid var(--line);font-size:12px}}
@media(max-width:850px){{.cards,.grid,.notes{{grid-template-columns:1fr}}
.theme-box{{grid-template-columns:1fr}}.wrap{{padding:20px 14px}}
table{{font-size:12px}}}}
</style></head><body><main class="wrap">
<header><p class="kicker">{_date_dash(artifact.signal_date)} · DAILYWATCH20 / INTERNAL AUDIT</p>
<h1>今日20只重点关注</h1>
<p class="meta">源数据 {_date_dash(artifact.source_date)} · {model} · {feature_set}</p>
<span class="status">PASSED · 正式 4+16 artifact</span></header>
<section class="cards">
<div class="card"><small>跟踪池</small><strong>20 只</strong><p>总跟踪权重 100%</p></div>
<div class="card"><small>A 袖 · 聚焦</small><strong class="a">4 只</strong><p>{a_weight:.1%}</p></div>
<div class="card"><small>B 袖 · 分散</small><strong class="b">16 只</strong><p>{b_weight:.1%}</p></div>
<div class="card"><small>数据合同</small><strong>PASSED</strong>
<p>{html.escape(_minute_summary(artifact.receipt))}</p></div></section>
<section class="grid">
<div class="panel"><h2>行业权重 Top 8</h2>{_industry_bars(industry)}</div>
<div class="panel"><h2>主题权重</h2><div class="theme-box">
<div class="donut" style="background:{_donut_style(themes)}"></div>
<div>{_theme_legend(themes)}</div></div></div></section>
<section class="panel table-panel"><div class="table-head">
<h2>A4 · 模型探索</h2><span class="a">{a_weight:.1%}</span></div>
<table><thead><tr><th>排名</th><th>股票</th><th>行业</th><th>主题</th>
<th>权重</th><th>综合分</th><th>状态</th></tr></thead>
<tbody>{_html_table(artifact.a_frame)}</tbody></table></section>
<section class="panel table-panel"><div class="table-head">
<h2>B16 · 约束观察</h2><span class="b">{b_weight:.1%}</span></div>
<table><thead><tr><th>排名</th><th>股票</th><th>行业</th><th>主题</th>
<th>权重</th><th>综合分</th><th>状态</th></tr></thead>
<tbody>{_html_table(artifact.b_frame)}</tbody></table></section><section class="notes">
<div class="panel"><h2>主要驱动</h2><ul>
{"".join(f"<li>{html.escape(item)}</li>" for item in drivers) or "<li>artifact 未提供</li>"}
</ul></div><div class="panel"><h2>主要风险</h2><ul>
{"".join(f"<li>{html.escape(item)}</li>" for item in risks) or "<li>artifact 未提供</li>"}
</ul></div><div class="panel"><h2>Regime 摘要</h2>
<p>{html.escape(_regime_summary(artifact.receipt))}</p></div></section>
<footer>纯 artifact 展示层 · 不在 market-intel 内重新打分或选股 · 仅供研究观察</footer>
</main></body></html>"""


def build_daily_watch20_html(
    artifact: DailyWatch20Artifact,
    *,
    audience: str = "client",
) -> str:
    """Build the audience-specific DailyWatch20 HTML report."""

    if audience == "client":
        from .daily_watch20_client_render import build_daily_watch20_client_html

        return build_daily_watch20_client_html(artifact)
    if audience != "internal":
        raise ValueError("DailyWatch20 audience must be 'client' or 'internal'.")
    frame = artifact.frame
    industry = _group_weights(frame, "industry").head(8)
    themes = _top_with_other(_group_weights(frame, "theme"), limit=7)
    a_weight = float(artifact.a_frame["tracking_weight"].sum())
    b_weight = float(artifact.b_frame["tracking_weight"].sum())
    drivers = _top_text_items(frame, "top_drivers")
    risks = _top_text_items(frame, "primary_risk")
    model = html.escape(str(artifact.receipt.get("model_version") or ""))
    feature_set = html.escape(str(artifact.receipt.get("feature_set_id") or ""))
    return _build_internal_html_document(
        artifact=artifact,
        industry=industry,
        themes=themes,
        a_weight=a_weight,
        b_weight=b_weight,
        drivers=drivers,
        risks=risks,
        model=model,
        feature_set=feature_set,
    )


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _truncate(value: Any, width: int) -> str:
    text = str(value or "-").strip()
    if len(text) <= width:
        return text
    return text[: max(width - 1, 0)] + "…"


def _table_rows(frame: pd.DataFrame) -> list[list[str]]:
    return [
        [
            str(int(row["rank"])),
            _truncate(row["name"], 10),
            str(row["symbol"]),
            _truncate(row["industry"], 10),
            _truncate(row["theme"], 15),
            f"{float(row['tracking_weight']):.1%}",
            _score_text(row["final_score"]),
            "NEW" if bool(row["is_new"]) else ("双确认" if bool(row["dual_confirmed"]) else "-"),
        ]
        for row in _records(frame)
    ]


def _draw_table(ax: Any, frame: pd.DataFrame, *, title: str, color: str, font: Any) -> None:
    from a_share_daily.charts.theme import FG, LINE, MUTED, PANEL, PANEL_ALT

    ax.axis("off")
    ax.set_title(title, loc="left", color=color, fontsize=15, fontproperties=font, pad=10)
    table = ax.table(
        cellText=_table_rows(frame),
        colLabels=["排名", "名称", "代码", "行业", "主题", "权重", "综合分", "状态"],
        cellLoc="left",
        colLoc="left",
        colWidths=[0.05, 0.10, 0.12, 0.12, 0.20, 0.08, 0.08, 0.09],
        bbox=(0, 0, 1, 0.94),
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    for (row, _column), cell in table.get_celld().items():
        cell.set_edgecolor(LINE)
        cell.set_linewidth(0.6)
        cell.set_facecolor(PANEL_ALT if row == 0 else (PANEL if row % 2 else "#fbfaf6"))
        cell.get_text().set_color(MUTED if row == 0 else FG)
        if font is not None:
            cell.get_text().set_fontproperties(font)


def _draw_summary_header(fig: Any, artifact: DailyWatch20Artifact, *, font: Any) -> None:
    from a_share_daily.charts.theme import ACCENT, DOWN, FG, MUTED, YELLOW, add_report_header

    frame = artifact.frame
    a_weight = float(artifact.a_frame["tracking_weight"].sum())
    b_weight = float(artifact.b_frame["tracking_weight"].sum())
    add_report_header(
        fig,
        kicker="DAILYWATCH20 / INTERNAL AUDIT",
        title=f"今日20只重点关注 · {_date_dash(artifact.signal_date)}",
        subtitle=(
            "source "
            f"{_date_dash(artifact.source_date)} · "
            f"{_truncate(artifact.receipt.get('model_version'), 34)} · receipt PASSED"
        ),
        title_size=24,
    )
    cards = (
        ("跟踪池", f"{len(frame)} 只 · 100%", FG),
        ("A 袖", f"4 只 · {a_weight:.1%}", DOWN),
        ("B 袖", f"16 只 · {b_weight:.1%}", ACCENT),
        ("Regime", _truncate(_regime_summary(artifact.receipt), 18), YELLOW),
    )
    for index, (label, value, color) in enumerate(cards):
        x = 0.055 + index * 0.235
        fig.text(x, 0.815, label, fontsize=8.5, color=MUTED, fontproperties=font)
        fig.text(
            x,
            0.79,
            value,
            fontsize=12.5,
            color=color,
            fontproperties=font,
            fontweight="bold",
        )


def _draw_distribution(
    ax_industry: Any, ax_theme: Any, artifact: DailyWatch20Artifact, font: Any
) -> None:
    from a_share_daily.charts.theme import BG, BLUE_SCALE, FG, MUTED, style_plot_axes

    industry = _group_weights(artifact.frame, "industry").head(8).sort_values()
    colors = list(reversed(BLUE_SCALE[: len(industry)]))
    style_plot_axes(ax_industry, grid_axis="x", panel_alpha=0.68)
    ax_industry.barh(range(len(industry)), industry.values, color=colors, height=0.62)
    ax_industry.set_yticks(
        range(len(industry)), labels=[_truncate(item, 7) for item in industry.index]
    )
    ax_industry.set_xticks([])
    ax_industry.set_title(
        "行业权重 Top 8", loc="left", fontsize=15, color=FG, fontproperties=font, pad=12
    )
    for idx, value in enumerate(industry.values):
        ax_industry.text(
            float(value) + 0.003,
            idx,
            f"{float(value):.1%}",
            va="center",
            fontsize=9,
            color=FG,
        )
    for label in ax_industry.get_yticklabels():
        if font is not None:
            label.set_fontproperties(font)

    themes = _top_with_other(_group_weights(artifact.frame, "theme"), limit=7)
    style_plot_axes(ax_theme, grid_axis=None, panel_alpha=0.68)
    wedges, _ = ax_theme.pie(
        themes.values,
        startangle=90,
        counterclock=False,
        colors=BLUE_SCALE[: len(themes)],
        wedgeprops={"width": 0.38, "edgecolor": BG, "linewidth": 2},
    )
    ax_theme.text(0, 0.06, "20", ha="center", va="center", fontsize=22, color=FG)
    ax_theme.text(
        0, -0.15, "只", ha="center", va="center", fontsize=9, color=MUTED, fontproperties=font
    )
    ax_theme.set_title("主题权重", loc="left", fontsize=15, color=FG, fontproperties=font, pad=12)
    legend_labels = [
        f"{_truncate(label, 14)} {float(value):.1%}" for label, value in themes.items()
    ]
    ax_theme.legend(
        wedges,
        legend_labels,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.26),
        ncol=2,
        frameon=False,
        fontsize=7,
        prop=font,
        labelcolor=FG,
    )


def _draw_note_panel(ax: Any, title: str, items: Sequence[str], *, color: str, font: Any) -> None:
    from a_share_daily.charts.theme import FG

    ax.axis("off")
    ax.set_title(title, loc="left", fontsize=14, color=color, fontproperties=font, pad=8)
    lines = items or ["artifact 未提供"]
    text = "\n".join(f"{index}. {_truncate(item, 48)}" for index, item in enumerate(lines, 1))
    ax.text(
        0.01,
        0.94,
        text,
        transform=ax.transAxes,
        va="top",
        fontsize=9,
        linespacing=1.55,
        color=FG,
        fontproperties=font,
    )


def artifact_summary(artifact: DailyWatch20Artifact) -> dict[str, Any]:
    return {
        "status": "passed",
        "schema_version": artifact.receipt.get("schema_version"),
        "root": str(artifact.root),
        "data_path": str(artifact.data_path),
        "receipt_path": str(artifact.receipt_path),
        "source_date": artifact.source_date,
        "signal_date": artifact.signal_date,
        "counts": {
            "total": len(artifact.frame),
            "a": len(artifact.a_frame),
            "b": len(artifact.b_frame),
            "unique": int(artifact.frame["symbol"].nunique()),
        },
        "tracking_weight_sum": float(artifact.frame["tracking_weight"].sum()),
        "model_version": artifact.receipt.get("model_version"),
        "feature_set_id": artifact.receipt.get("feature_set_id"),
    }


__all__ = [
    "DEFAULT_WATCHLIST20_ROOT",
    "DailyWatch20Artifact",
    "DailyWatch20RenderResult",
    "DailyWatch20ValidationError",
    "artifact_summary",
    "build_daily_watch20_html",
    "load_daily_watch20",
    "resolve_watchlist20_root",
]
