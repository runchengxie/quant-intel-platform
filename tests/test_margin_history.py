import pandas as pd
import pytest

from a_share_daily import pipeline
from a_share_daily.charts.public_export import _chart_card
from a_share_daily.charts.public_extract import _dashboard


def test_margin_history_uses_one_comparable_exchange_scope(monkeypatch):
    frames = {
        "20260924": pd.DataFrame({"exchange_id": ["SSE", "BSE"], "rzye": [100e8, 5e8]}),
        "20260930": pd.DataFrame({"exchange_id": ["SSE"], "rzye": [90e8]}),
    }
    monkeypatch.setattr(pipeline, "_latest_partition_dates", lambda *args, **kwargs: list(frames))
    monkeypatch.setattr(pipeline.D, "read_margin", frames.__getitem__)
    rows = pipeline._recent_margin_data("20260930")
    assert [row["rzye"] for row in rows] == [100.0, 90.0]
    assert all(row["exchange_scope"] == "SSE" for row in rows)


def test_margin_history_rejects_duplicate_exchange_rows(monkeypatch):
    monkeypatch.setattr(pipeline, "_latest_partition_dates", lambda *args, **kwargs: ["20260930"])
    monkeypatch.setattr(
        pipeline.D,
        "read_margin",
        lambda day: pd.DataFrame({"exchange_id": ["SSE", "SSE"], "rzye": [1, 2]}),
    )
    with pytest.raises(ValueError, match="duplicate"):
        pipeline._recent_margin_data("20260930")


def test_dashboard_financing_points_identify_partial_exchange_coverage():
    inputs = {
        "daily": pd.DataFrame({"pct_chg": [1, -1]}),
        "limit_up_observed": False,
        "max_board_observed": False,
        "turnover": pd.DataFrame(),
        "margin": pd.DataFrame([{"date": "20260930", "rzye": 90.0, "exchange_scope": "SSE"}]),
    }
    source = {"date": "2026-09-30", "source_label": "Tushare", "source_url": "https://tushare.pro"}
    points = _dashboard(inputs, source)
    margin = next(point for point in points if point["label"].startswith("融资余额"))
    assert "SSE" in margin["source_label"]
    assert "部分交易所" in margin["source_label"]


def test_partial_margin_candidate_is_degraded_even_when_current():
    from datetime import date

    point = {"label": "融资余额 2026-09-30", "source_label": "Tushare（部分交易所，覆盖 SSE）"}
    card = _chart_card(
        "dashboard",
        kind="evening",
        target=date(2026, 9, 30),
        points=[point],
        ok={"dashboard"},
        degraded=set(),
        failed=set(),
        skipped=set(),
        errors={},
    )
    assert card["status"] == "degraded"
    assert "部分交易所" in card["reason"]


def test_margin_history_converts_numeric_strings_before_aggregation():
    from a_share_daily.charts.margin_history import comparable_margin_rows

    rows = comparable_margin_rows(
        {
            "20260930": pd.DataFrame(
                {"exchange_id": ["SSE", "SZSE"], "rzye": ["100000000", "200000000"]}
            )
        }
    )
    assert rows[0]["rzye"] == 3.0


def test_private_financing_plot_identifies_its_exchange_scope():
    import matplotlib.pyplot as plt

    from a_share_daily.charts.dashboard import _draw_margin_panel

    figure, axis = plt.subplots()
    try:
        _draw_margin_panel(
            axis, pd.DataFrame([{"date": "20260930", "rzye": 90.0, "exchange_scope": "SSE"}])
        )
        assert "SSE" in axis.get_title(loc="left")
    finally:
        plt.close(figure)


def test_weekly_text_does_not_present_partial_scope_as_full_market(monkeypatch, tmp_path):
    frames = {
        day: pd.DataFrame({"pct_chg": [1.0, -1.0], "amount": [1e5, 2e5]})
        for day in ["20260924", "20260930"]
    }
    monkeypatch.setattr(pipeline, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(pipeline, "_weekly_gold_prices", lambda days: {})
    monkeypatch.setattr(
        pipeline.D,
        "read_margin",
        lambda day: pd.DataFrame(
            {"exchange_id": ["SSE"], "rzye": [100e8 if day == "20260924" else 90e8]}
        ),
    )
    state = pipeline._ChartState("20260930")
    pipeline._run_weekly_text(state, list(frames), frames)
    assert state.results.get("weekly_text"), state.errors
    assert "融资余额从" not in (tmp_path / "weekly_recap.md").read_text()
