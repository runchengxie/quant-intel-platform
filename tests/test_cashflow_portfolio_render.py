from __future__ import annotations

from pathlib import Path

from a_share_daily.cashflow_portfolio_render import (
    enrich_cashflow_portfolio,
    render_cashflow_portfolio_markdown,
    render_cashflow_portfolio_png,
)


def _artifact() -> dict[str, object]:
    return {
        "strategy_id": "cashflow_quality_top50_v1",
        "policy_id": "cashflow_quality_top50_v1.quarterly_fcf_cap10.v1",
        "source_date": "20260904",
        "signal_date": "20260907",
        "pit_quality": "reconstructed",
        "research_only": True,
        "eligible_for_live": False,
        "candidate_count": 58,
        "selected_count": 3,
        "targets": [
            {"symbol": "000001.SZ", "name": "ç²", "selection_rank": 1, "target_weight": 0.5},
            {"symbol": "000002.SZ", "name": "ä¹", "selection_rank": 2, "target_weight": 0.3},
            {"symbol": "000003.SZ", "name": "ä¸", "selection_rank": 3, "target_weight": 0.2},
        ],
    }


def test_portfolio_markdown_contains_real_holdings_and_pit_warning() -> None:
    markdown = render_cashflow_portfolio_markdown(_artifact())

    assert "000001" in markdown
    assert "50.0%" in markdown
    assert "RECONSTRUCTED PIT" in markdown
    assert "ç ç©¶å¿«ç§" in markdown
    assert "eligible_for_live=false" in markdown


def test_portfolio_can_enrich_company_names_from_pinned_instrument_snapshot(tmp_path: Path) -> None:
    instruments = tmp_path / "instruments.parquet"
    import pandas as pd

    pd.DataFrame(
        {
            "symbol": ["000001.SZ", "000002.SZ"],
            "name": ["å¹³å®é¶è¡", "ä¸ç§A"],
            "industry": ["é¶è¡", "å¨å½å°äº§"],
        }
    ).to_parquet(instruments, index=False)

    enriched = enrich_cashflow_portfolio(_artifact(), instruments)
    markdown = render_cashflow_portfolio_markdown(enriched)

    assert enriched["instrument_snapshot"] == str(instruments.resolve())
    assert enriched["targets"][0]["name"] == "å¹³å®é¶è¡"
    assert enriched["targets"][0]["industry"] == "é¶è¡"
    assert "å¹³å®é¶è¡" in markdown
    assert "ä¸ç§A" in markdown
    assert enriched["instrument_snapshot_sha256"]


def test_portfolio_markdown_contains_industry_breakdown() -> None:
    artifact = _artifact()
    artifact["targets"] = [
        {**row, "industry": industry}
        for row, industry in zip(
            artifact["targets"], ["é¶è¡", "é¶è¡", "å»è¯"], strict=True
        )
    ]

    markdown = render_cashflow_portfolio_markdown(artifact)

    assert "è¡ä¸åå¸" in markdown
    assert "é¶è¡" in markdown
    assert "80.0%" in markdown


def test_portfolio_png_is_written_as_a_real_chart(tmp_path: Path) -> None:
    output = render_cashflow_portfolio_png(_artifact(), tmp_path / "portfolio.png")

    assert output.is_file()
    assert output.read_bytes().startswith(b"\x89PNG")
    assert output.stat().st_size > 10_000


def _executable_artifact() -> dict[str, object]:
    artifact = _artifact()
    artifact.update(
        {
            "schema_version": "strategy_app.cashflow.executable.v1",
            "price_date": "20260904",
            "policy": {
                "portfolio_value": 500_000.0,
                "cash_reserve": 0.03,
                "max_holdings": 25,
            },
            "invested_amount": 470_000.0,
            "cash_amount": 30_000.0,
            "invested_weight": 0.94,
            "skipped": [{"symbol": "000004.SZ", "reason": "missing_price"}],
        }
    )
    artifact["targets"] = [
        {
            **row,
            "industry": industry,
            "price": price,
            "target_amount": target,
            "shares": shares,
            "actual_amount": actual,
            "actual_weight": actual / 500_000,
            "weight_deviation": actual / 500_000 - row["target_weight"],
        }
        for row, industry, price, target, shares, actual in zip(
            artifact["targets"],
            ["é¶è¡", "é¶è¡", "å»è¯"],
            [20.0, 40.0, 50.0],
            [250_000.0, 150_000.0, 100_000.0],
            [12_500, 3_700, 2_000],
            [250_000.0, 148_000.0, 100_000.0],
            strict=True,
        )
    ]
    return artifact


def test_executable_markdown_contains_tradeability_diagnostics() -> None:
    markdown = render_cashflow_portfolio_markdown(_executable_artifact())

    assert "å¯æ§è¡ç»å" in markdown
    assert "ç°é" in markdown
    assert "å®éè¡æ°" in markdown
    assert "æéåå·®" in markdown
    assert "missing_price" in markdown


def test_executable_png_uses_top_holdings_and_execution_kpis(tmp_path: Path) -> None:
    output = render_cashflow_portfolio_png(_executable_artifact(), tmp_path / "executable.png")

    assert output.is_file()
    assert output.stat().st_size > 10_000

