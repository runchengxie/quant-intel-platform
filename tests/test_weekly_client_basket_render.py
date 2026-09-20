from __future__ import annotations

from pathlib import Path

from PIL import Image

from a_share_daily.weekly_client_basket import SourcePosition, compose_weekly_basket
from a_share_daily.weekly_client_basket_render import (
    render_basket_csv,
    render_basket_markdown,
    write_rendered_outputs,
)


def _source(symbol: str, strategy: str, rank: int) -> SourcePosition:
    return SourcePosition(
        symbol=symbol,
        name=f"Name {symbol}",
        source_strategy=strategy,
        source_product=f"{strategy}.v1",
        signal_date="20260911",
        valid_until="20260918",
        rank=rank,
        score=1.0 / rank,
        selection_reason="render fixture",
        artifact_path=f"/tmp/{strategy}.json",
        artifact_sha256="b" * 64,
        research_only=strategy != "dailywatch_family",
        eligible_for_live=strategy == "dailywatch_family",
    )


def _artifact():
    sources = {
        "dailywatch_family": [_source(f"DW{i:03d}", "dailywatch_family", i) for i in range(1, 5)],
        "cashflow": [_source(f"CF{i:03d}", "cashflow", i) for i in range(1, 7)],
        "microcap": [_source(f"MC{i:03d}", "microcap", i) for i in range(1, 5)],
    }
    return compose_weekly_basket(sources, as_of_date="20260914")


def test_markdown_contains_ten_positions_and_shadow_disclaimer() -> None:
    text = render_basket_markdown(_artifact())

    assert "Weekly Client Basket 10" in text
    table_rows = [
        line
        for line in text.splitlines()
        if line.startswith("| ") and line.split("|")[1].strip().isdigit()
    ]
    assert len(table_rows) == 10
    assert "NEW" in text
    assert "KEEP" in text
    assert "DROP: 无" in text
    assert "research shadow" in text
    assert "DailyWatch" not in text


def test_csv_columns_are_stable() -> None:
    text = render_basket_csv(_artifact())

    assert text.splitlines()[0].split(",") == [
        "symbol",
        "name",
        "source_strategy",
        "source_product",
        "status",
        "signal_date",
        "valid_until",
        "rank",
        "score",
        "research_only",
    ]
    assert len(text.splitlines()) == 11


def test_write_rendered_outputs_creates_markdown_and_csv(tmp_path: Path) -> None:
    paths = write_rendered_outputs(_artifact(), tmp_path)

    assert paths["markdown"].exists()
    assert paths["csv"].exists()
    assert paths["png"].exists()
    with Image.open(paths["png"]) as image:
        width, height = image.size
    assert 0.75 <= width / height <= 1.0
    assert height < 2_500


def test_markdown_and_png_accept_provider_performance_artifact(tmp_path: Path) -> None:
    performance = {
        "schema_version": "weekly_basket.performance.v2",
        "report_date": "20260914",
        "status": "ok",
        "series": [
            {"date": "2024-09-24", "nav": 1.0},
            {"date": "2026-09-14", "nav": 1.2},
        ],
        "benchmark": [
            {"date": "2024-09-24", "nav": 1.0},
            {"date": "2026-09-14", "nav": 1.1},
        ],
        "benchmark_name": "沪深300价格指数（不含股息）",
        "metrics": {
            "total_return": 0.2,
            "annualized_return": 0.095,
            "max_drawdown": -0.18,
            "observations": 145,
            "mean_turnover": 0.1,
        },
        "evidence_tier": "reconstructed_proxy",
        "methodology": {
            "method": "weekly_64_reconstructed_pit_proxy",
            "cost_bps": 10.0,
            "limitations": ["period_return_replay"],
        },
        "execution_audit": {
            "missing_price_count": 2,
            "missing_entry_price_count": 1,
            "missing_exit_price_count": 1,
            "untradable_count": 1,
            "average_realized_position_count": 9.8,
            "average_cash_weight": 0.02,
            "max_cash_weight": 0.1,
            "blocked_dates": ["2025-01-06"],
            "preserve_gross_exposure": True,
        },
    }

    text = render_basket_markdown(_artifact(), performance=performance)
    paths = write_rendered_outputs(_artifact(), tmp_path, performance=performance)

    assert "累计 +20.00%" in text
    assert "现金流 6" in text
    assert "微盘 4" in text
    assert "历史时点重建回测" in text
    assert "按各历史时点当时可得信息重建" in text
    assert "PIT 拟合回测" not in text
    assert "年化收益：+9.50%" in text
    assert "最大回撤：-18.00%" in text
    assert "145 期" in text
    assert "净值截止：2026-09-14" in text
    assert "沪深300价格指数（不含股息）" in text
    assert "60/40" in text and "袖内等权" in text
    assert "10.0 bps" in text
    assert "下一交易日开盘" in text
    assert "缺价权重保留为现金" in text
    assert "无逐笔 broker ledger" in text
    assert "Research Observation · 不代表实盘历史 · 不构成投资建议" in text
    assert paths["png"].stat().st_size > 1_000
    with Image.open(paths["png"]) as image:
        width, height = image.size
    assert 0.75 <= width / height <= 1.0
    assert height < 2_500
