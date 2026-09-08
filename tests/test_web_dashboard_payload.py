"""Unit tests for daily_messenger.dashboard.payload core functions."""

import json
from pathlib import Path

import pytest

from daily_messenger.dashboard import payload as pmod


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


# ── _number / _rounded ──


def test_number_handles_numeric_types() -> None:
    assert pmod._number(42) == 42.0
    assert pmod._number(3.14) == 3.14
    assert pmod._number("-5.5") == -5.5
    assert pmod._number("  1.23  ") == 1.23


def test_number_rejects_non_numeric() -> None:
    assert pmod._number(None) is None
    assert pmod._number(True) is None
    assert pmod._number(False) is None
    assert pmod._number("hello") is None
    assert pmod._number("") is None
    assert pmod._number([]) is None


def test_number_rejects_nan_and_inf() -> None:
    assert pmod._number(float("nan")) is None
    assert pmod._number(float("inf")) is None
    assert pmod._number(float("-inf")) is None


def test_rounded_returns_none_for_non_number() -> None:
    assert pmod._rounded(None) is None
    assert pmod._rounded("abc") is None


def test_rounded_truncates_to_digits() -> None:
    assert pmod._rounded(3.14159, 2) == 3.14
    assert pmod._rounded(3.14159, 4) == 3.1416


# ── _coerce_row_value ──


def test_coerce_row_value_converts_numeric_strings() -> None:
    assert pmod._coerce_row_value("42.5") == 42.5
    assert pmod._coerce_row_value("  0.1  ") == 0.1


def test_coerce_row_value_preserves_text() -> None:
    assert pmod._coerce_row_value("hello") == "hello"
    assert pmod._coerce_row_value(None) == ""


# ── _latest_panel_row ──


def test_latest_panel_row_finds_last_row_with_data() -> None:
    rows = [
        {"date": "2024-01-01", "own_risk_appetite_score": None},
        {"date": "2024-01-02", "own_risk_appetite_score": "55"},
    ]
    result = pmod._latest_panel_row(rows)
    assert result["date"] == "2024-01-02"


def test_latest_panel_row_returns_empty_when_no_data() -> None:
    rows = [{"date": "2024-01-01", "vix": None}]
    result = pmod._latest_panel_row(rows)
    assert result == {}


# ── _chart_rows ──


def test_chart_rows_includes_only_recent_and_non_empty() -> None:
    rows: list[dict[str, object]] = []
    for i in range(800):
        rows.append(
            {
                "date": f"2024-{i % 12 + 1:02d}-{(i % 28) + 1:02d}",
                "own_risk_appetite_score": 50 + i % 30,
                "vix": 15 + i % 10,
            }
        )
    result = pmod._chart_rows(pmod.PanelDocument(path=None, exists=True, rows=rows))
    assert len(result) <= pmod.CHART_ROW_LIMIT
    # All rows should have date and at least one value
    for row in result:
        assert "date" in row
        assert any(v is not None for k, v in row.items() if k != "date")


def test_chart_rows_skips_rows_without_date() -> None:
    rows = [
        {"own_risk_appetite_score": 50},
        {"date": "2024-01-02", "own_risk_appetite_score": 60},
    ]
    result = pmod._chart_rows(pmod.PanelDocument(path=None, exists=True, rows=rows))
    assert len(result) == 1
    assert result[0]["date"] == "2024-01-02"


# ── _similar_state_neighbors ──


def _make_panel_rows(count: int, *, include_returns: bool = True) -> list[dict[str, object]]:
    """Build synthetic state panel rows with realistic values."""
    rows: list[dict[str, object]] = []
    for i in range(count):
        row: dict[str, object] = {
            "date": f"2024-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}",
            "own_risk_appetite_score": 50 + i % 30,
            "rsp_spy_participation_proxy": 0.01 + (i % 5) * 0.005,
            "valuation_rate_gap_proxy": 0.5 + (i % 10) * 0.2,
            "vix": 15 + i % 10,
        }
        if include_returns:
            row["spy_forward_return_fwd_90d"] = 0.02 + (i % 3) * 0.01
            row["spy_forward_return_fwd_252d"] = 0.08 + (i % 5) * 0.02
            row["spy_forward_return_fwd_1260d"] = 0.4 + (i % 3) * 0.1
            row["spy_forward_return_fwd_2520d"] = 0.7 + i * 0.05
        rows.append(row)
    return rows


def test_similar_state_neighbors_requires_min_rows() -> None:
    empty_panel = pmod.PanelDocument(path=None, exists=True, rows=[])
    assert pmod._similar_state_neighbors(empty_panel) == []

    two_row_panel = pmod.PanelDocument(path=None, exists=True, rows=_make_panel_rows(2))
    assert pmod._similar_state_neighbors(two_row_panel) == []


def test_similar_state_neighbors_returns_up_to_limit() -> None:
    rows = _make_panel_rows(20)
    panel = pmod.PanelDocument(path=None, exists=True, rows=rows)
    neighbors = pmod._similar_state_neighbors(panel)
    assert 1 <= len(neighbors) <= pmod.NEIGHBOR_LIMIT


def test_similar_state_neighbors_excludes_latest_row() -> None:
    rows = _make_panel_rows(10)
    panel = pmod.PanelDocument(path=None, exists=True, rows=rows)
    latest_row = pmod._latest_panel_row(rows)
    latest_date = latest_row.get("date")
    neighbors = pmod._similar_state_neighbors(panel)
    neighbor_dates = {n["date"] for n in neighbors}
    assert latest_date not in neighbor_dates


def test_similar_state_neighbors_includes_forward_returns() -> None:
    rows = _make_panel_rows(10, include_returns=True)
    panel = pmod.PanelDocument(path=None, exists=True, rows=rows)
    neighbors = pmod._similar_state_neighbors(panel)
    for neighbor in neighbors:
        assert "forwardReturn3M" in neighbor
        assert "forwardReturn1Y" in neighbor


def test_similar_state_neighbors_requires_min_dimensions() -> None:
    rows: list[dict[str, object]] = []
    for i in range(5):
        rows.append(
            {
                "date": f"2024-01-0{i + 1}",
                "own_risk_appetite_score": 50 + i,  # only 1 dimension
            }
        )
    panel = pmod.PanelDocument(path=None, exists=True, rows=rows)
    # Only 1 dimension available, needs >= 2
    assert pmod._similar_state_neighbors(panel) == []


# ── _neighbor_summary ──


def test_neighbor_summary_computes_stats() -> None:
    neighbors = [
        {"forwardReturn3M": 0.03, "forwardReturn1Y": 0.1},
        {"forwardReturn3M": -0.01, "forwardReturn1Y": 0.05},
        {"forwardReturn3M": 0.05, "forwardReturn1Y": 0.15},
    ]
    summary = pmod._neighbor_summary(neighbors)
    assert len(summary) == 2  # 3M and 1Y

    summary_3m = next(s for s in summary if s["horizon"] == "3M")
    assert summary_3m["count"] == 3
    assert summary_3m["average"] is not None
    assert summary_3m["median"] is not None
    # 2 out of 3 are positive
    assert summary_3m["positiveRate"] == pytest.approx(2 / 3, abs=0.01)


def test_neighbor_summary_empty_when_no_forward_returns() -> None:
    neighbors: list[dict[str, object]] = [
        {"otherField": 42},
    ]
    assert pmod._neighbor_summary(neighbors) == []


# ── _theme_cards ──


def test_theme_cards_sorts_by_total_descending() -> None:
    scores = {
        "themes": [
            {"name": "b", "label": "B", "total": 50, "breakdown": {"fundamental": 50}},
            {"name": "a", "label": "A", "total": 80, "breakdown": {"fundamental": 80}},
            {"name": "c", "label": "C", "total": 30, "breakdown": {"fundamental": 30}},
        ]
    }
    cards = pmod._theme_cards(scores)
    assert [c["name"] for c in cards] == ["a", "b", "c"]


def test_theme_cards_handles_degraded_theme() -> None:
    scores = {
        "themes": [
            {"name": "test", "label": "Test", "total": 50, "degraded": True, "breakdown": {}},
        ]
    }
    cards = pmod._theme_cards(scores)
    assert cards[0]["degraded"] is True


# ── build_payload ──


def test_build_payload_missing_all_sources(tmp_path: Path) -> None:
    payload = pmod.build_payload(out_dir=tmp_path / "out", snapshot_dir=tmp_path / "snapshots")
    assert payload["title"] == "市场全景终端"
    assert payload["coverage"]
    # All coverage statuses should be "missing"
    coverage = {row["key"]: row["status"] for row in payload["coverage"]}
    assert coverage["daily_scores"] == "missing"
    assert coverage["cross_market"] == "missing"


def test_build_payload_includes_chart_series(tmp_path: Path) -> None:
    payload = pmod.build_payload(out_dir=tmp_path / "out", snapshot_dir=tmp_path / "snapshots")
    assert "chartSeries" in payload
    assert len(payload["chartSeries"]) == 4
    series_fields = {s["field"] for s in payload["chartSeries"]}
    assert "own_risk_appetite_score" in series_fields
    assert "vix" in series_fields
    for s in payload["chartSeries"]:
        assert "field" in s
        assert "label" in s
        assert "color" in s


def test_build_payload_chart_rows_empty_when_no_panel(tmp_path: Path) -> None:
    payload = pmod.build_payload(out_dir=tmp_path / "out", snapshot_dir=tmp_path / "snapshots")
    assert payload["chartRows"] == []


def test_build_payload_derives_free_source_state_panel(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    snapshot_dir = tmp_path / "snapshots"
    _write_json(
        out_dir / "scores.json",
        {
            "date": "2026-07-02",
            "themes": [
                {"name": "ai", "label": "AI", "total": 60, "breakdown": {"valuation": 40}},
                {"name": "btc", "label": "BTC", "total": 50, "breakdown": {"valuation": 50}},
            ],
        },
    )
    _write_json(
        out_dir / "raw_market.json",
        {
            "date": "2026-07-02",
            "market": {"indices": [{"symbol": "SPX", "close": 6200.0}]},
            "sentiment": {
                "put_call": {"source": "cboe_daily_market_statistics", "equity": 0.65},
                "aaii": {"bullish_pct": 39.0, "bearish_pct": 31.0},
            },
        },
    )
    _write_json(
        snapshot_dir / "cross_market_snapshot.json",
        {
            "date": "20260702",
            "us_stocks": {
                "SPY": {"close": 620.0, "pct_chg": 0.2},
                "QQQ": {"close": 540.0, "pct_chg": 1.2},
            },
            "macros": {
                "^VIX": {"close": 16.0, "source": "fred"},
                "^TNX": {"close": 4.45, "source": "fred"},
            },
        },
    )

    payload = pmod.build_payload(out_dir=out_dir, snapshot_dir=snapshot_dir)

    coverage = {row["key"]: row["status"] for row in payload["coverage"]}
    assert coverage["risk_state"] == "proxy"
    assert coverage["participation"] == "proxy"
    assert coverage["valuation_state"] == "proxy"
    assert payload["latest"]["riskAppetite"] == pytest.approx(66.67, abs=0.01)
    assert payload["latest"]["participation"] == -0.01
    assert payload["latest"]["valuationRateGap"] == pytest.approx(0.25, abs=0.01)
    assert len(payload["chartRows"]) == 1
    assert payload["sourceManifest"][-1]["path"] == "derived:free-source-proxy"
    sentiment = {row["key"]: row for row in payload["terminal"]["sentimentCards"]}
    assert sentiment["fear_greed_proxy"]["status"] == "proxy"
    assert "Cboe/FRED VIX" in sentiment["fear_greed_proxy"]["detail"]


def test_build_payload_neighbors_empty_when_no_panel(tmp_path: Path) -> None:
    payload = pmod.build_payload(out_dir=tmp_path / "out", snapshot_dir=tmp_path / "snapshots")
    assert payload["neighbors"] == []
    assert payload["neighborSummary"] == []


def test_build_payload_with_state_panel(tmp_path: Path) -> None:
    panel_path = tmp_path / "state_panel.csv"
    panel_path.write_text(
        "\n".join(
            [
                "date,own_risk_appetite_score,rsp_spy_participation_proxy,valuation_rate_gap_proxy,vix,spy_forward_return_fwd_90d,spy_forward_return_fwd_252d",
                "2024-01-02,58,0.012,0.8,18.4,0.03,0.08",
                "2024-02-02,64,0.018,0.6,16.9,0.02,0.06",
                "2024-03-02,41,-0.045,1.9,24.7,-0.02,0.01",
                "2024-04-02,66,0.021,0.5,17.2,0.03,0.07",
                "2024-05-02,55,0.008,1.2,20.1,0.01,0.04",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    payload = pmod.build_payload(
        out_dir=tmp_path / "out",
        snapshot_dir=tmp_path / "snapshots",
        state_panel_path=panel_path,
    )
    assert len(payload["chartRows"]) == 5
    assert len(payload["neighbors"]) >= 1
    assert len(payload["neighborSummary"]) >= 1
    assert payload["latest"]["riskAppetite"] == 55.0


# ── _json_default ──


def test_json_default_serializes_path() -> None:
    p = Path("tmp", "test")
    result = pmod._json_default(p)
    assert result == str(p)
    assert "test" in result


def test_json_default_raises_on_unknown_type() -> None:
    with pytest.raises(TypeError, match="not JSON serializable"):
        pmod._json_default(object())


def test_load_json_reports_decode_error(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_bytes(b"\xbf")

    doc = pmod._load_json(path)

    assert doc.exists is True
    assert doc.data == {}
    assert doc.error is not None
