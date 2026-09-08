from pathlib import Path

import pandas as pd

from daily_messenger.dashboard import state_panel
from daily_messenger.etl.fetchers.fred import FredObservation


def _sample_panel(rows: int = 320) -> pd.DataFrame:
    dates = pd.date_range("2024-01-02", periods=rows, freq="B")
    return pd.DataFrame(
        {
            "date": dates,
            "vix": [18 + idx * 0.01 for idx in range(rows)],
            "vvix": [90 + idx * 0.02 for idx in range(rows)],
            "put_call_equity": [0.72 + (idx % 9) * 0.01 for idx in range(rows)],
            "spy_close": [450 + idx * 0.3 for idx in range(rows)],
            "qqq_close": [380 + idx * 0.4 for idx in range(rows)],
            "rsp_close": [150 + idx * 0.08 for idx in range(rows)],
            "ten_year_yield": [4.0 + (idx % 30) * 0.01 for idx in range(rows)],
        }
    )


def test_enrich_state_panel_calculates_fitted_columns() -> None:
    result = state_panel.enrich_state_panel(_sample_panel())

    latest = result.iloc[-1]
    assert latest["date"] == "2025-03-24"
    assert latest["vol_structure"] > 0
    assert latest["own_risk_appetite_score"] > 0
    assert latest["own_risk_appetite_component_count"] >= 3
    assert latest["rsp_spy_participation_proxy"] == latest["rsp_spy_participation_proxy"]
    assert latest["valuation_rate_gap_proxy"] == latest["valuation_rate_gap_proxy"]
    assert latest["spy_high"] == latest["spy_close"]
    assert result.iloc[0]["spy_forward_return_fwd_90d"] > 0


def test_read_cboe_putcall_csv_skips_disclaimer_rows() -> None:
    text = "\n".join(
        [
            "Cboe disclaimer,,,,",
            ", PRODUCT: EQUITY,,EXCHANGE: Cboe,",
            "DATE,CALL,PUT,TOTAL,P/C Ratio",
            "01/02/2024,100,80,180,0.80",
            "01/03/2024,120,90,210,0.75",
        ]
    )

    result = state_panel._read_cboe_putcall_csv(text, "put_call_equity")

    assert result.to_dict("records") == [
        {"date": pd.Timestamp("2024-01-02"), "put_call_equity": 0.8},
        {"date": pd.Timestamp("2024-01-03"), "put_call_equity": 0.75},
    ]


def test_fetch_fred_series_uses_shared_fred_source(monkeypatch) -> None:
    calls: list[tuple[str, str | None, int]] = []

    def fake_fetch(series_id: str, *, start: str | None, timeout: int):
        calls.append((series_id, start, timeout))
        values = {"VIXCLS": 18.5, "DGS10": 4.2}
        return [
            FredObservation(date="2026-07-14", value=values[series_id]),
            FredObservation(date="2026-07-15", value=values[series_id] + 0.1),
        ]

    monkeypatch.setattr(state_panel, "fetch_observations", fake_fetch)

    result = state_panel.fetch_fred_series(start="2026-07-01", timeout=8)

    assert list(result.columns) == ["date", "vix", "ten_year_yield"]
    assert result.to_dict("records")[-1] == {
        "date": pd.Timestamp("2026-07-15"),
        "vix": 18.6,
        "ten_year_yield": 4.3,
    }
    assert calls == [
        ("VIXCLS", "2026-07-01", 8),
        ("DGS10", "2026-07-01", 8),
    ]


def test_calculate_breadth_preserves_named_date_index() -> None:
    close = pd.DataFrame(
        {
            "AAPL": [100 + idx for idx in range(220)],
            "MSFT": [110 + idx * 0.5 for idx in range(220)],
        },
        index=pd.date_range("2024-01-02", periods=220, freq="B", name="Date"),
    )

    result = state_panel._calculate_breadth(close, "spx")

    latest = result.iloc[-1]
    assert latest["date"] == pd.Timestamp("2024-11-04")
    assert latest["spx_above_20d_pct"] == 100
    assert latest["spx_above_50d_pct"] == 100
    assert latest["spx_above_200d_pct"] == 100
    assert latest["spx_breadth_component_count"] == 2


def test_build_state_panel_writes_csv_with_mocked_sources(tmp_path: Path, monkeypatch) -> None:
    sample = _sample_panel(120)
    empty = pd.DataFrame(columns=["date"])

    monkeypatch.setattr(
        state_panel,
        "fetch_fred_series",
        lambda *, start, timeout: sample[["date", "vix", "ten_year_yield"]],
    )
    monkeypatch.setattr(
        state_panel,
        "fetch_cboe_indices",
        lambda *, start, timeout: sample[["date", "vvix"]],
    )
    monkeypatch.setattr(
        state_panel,
        "fetch_put_call_history",
        lambda *, start, timeout: sample[["date", "put_call_equity"]],
    )
    monkeypatch.setattr(
        state_panel,
        "fetch_yfinance_prices",
        lambda *, period, start, timeout: sample[["date", "spy_close", "qqq_close", "rsp_close"]],
    )
    monkeypatch.setattr(state_panel, "fetch_breadth", lambda *args, **kwargs: empty)

    output = tmp_path / "market_state_panel.csv"
    result = state_panel.build_state_panel(
        output_path=output,
        period="1y",
        include_breadth=True,
        min_rows=10,
    )

    content = output.read_text(encoding="utf-8")
    assert result.path == output
    assert result.rows == 120
    assert "own_risk_appetite_score" in result.columns
    assert "valuation_rate_gap_proxy" in content
