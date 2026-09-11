from __future__ import annotations

from pathlib import Path

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
        "cashflow": [_source(f"CF{i:03d}", "cashflow", i) for i in range(1, 4)],
        "microcap": [_source(f"MC{i:03d}", "microcap", i) for i in range(1, 4)],
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
