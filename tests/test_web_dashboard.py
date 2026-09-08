import json
from pathlib import Path

from daily_messenger.dashboard import web_dashboard


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_state_panel(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "date,own_risk_appetite_score,rsp_spy_participation_proxy,valuation_rate_gap_proxy,vix,spy_close,sp500_close,ten_year_yield,hy_oas,own_risk_appetite_component_count,valuation_rate_gap_component_count,spy_forward_return_fwd_90d,spy_forward_return_fwd_252d,spy_forward_return_fwd_1260d,spy_forward_return_fwd_2520d",
                "2024-01-02,58,0.012,0.8,18.4,470.1,4750,4.2,3.4,5,2,0.031,0.082,0.42,0.78",
                "2024-02-02,64,0.018,0.6,16.9,482.5,4875,4.1,3.1,5,2,0.018,0.061,0.37,0.69",
                "2024-03-02,41,-0.045,1.9,24.7,461.8,4660,4.4,4.2,5,2,-0.022,0.014,0.21,0.48",
                "2024-04-02,66,0.021,0.5,17.2,489.0,4910,4.0,3.0,5,2,0.026,0.074,0.39,0.72",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _write_dashboard_outputs(out_dir: Path) -> None:
    _write_json(
        out_dir / "scores.json",
        {
            "date": "2024-04-02",
            "degraded": False,
            "themes": [
                {
                    "name": "ai",
                    "label": "AI",
                    "total": 82.0,
                    "breakdown": {"fundamental": 80, "valuation": 55},
                    "meta": {"delta": 4.5},
                }
            ],
        },
    )
    _write_json(
        out_dir / "actions.json",
        {
            "items": [
                {"action": "watch", "name": "AI", "reason": "score above watch threshold"},
            ]
        },
    )
    _write_json(
        out_dir / "raw_market.json",
        {
            "date": "2024-04-02",
            "market": {"indices": [{"symbol": "SPX", "close": 4910.0, "change_pct": 0.4}]},
        },
    )
    _write_json(
        out_dir / "etl_status.json",
        {
            "ok": True,
            "sources": [{"name": "market", "ok": True, "message": "synthetic"}],
        },
    )
    _write_json(
        out_dir / "raw_events.json",
        {
            "ai_updates": [
                {
                    "date": "2024-04-02",
                    "title": "Macro update",
                    "source": "test",
                    "url": "https://example.com/macro",
                    "sourceChain": [
                        {
                            "source": "Example",
                            "url": "https://example.com/macro",
                            "title": "Macro update",
                        }
                    ],
                }
            ]
        },
    )


def _write_dashboard_snapshots(snapshot_dir: Path) -> None:
    _write_json(
        snapshot_dir / "cross_market_snapshot.json",
        {
            "date": "20240402",
            "us_stocks": {"SPY": {"close": 489.0, "pct_chg": 0.5}},
            "commodities": {"GLD": {"close": 212.0, "pct_chg": -0.2}},
            "macros": {"^VIX": {"label": "VIX", "close": 17.2, "pct_chg": -3.0}},
            "concept_mapping": [
                {
                    "concept": "Semiconductors",
                    "avg_pct_chg": 1.4,
                    "signal": "bullish",
                    "drivers": ["NVDA +2.0%"],
                }
            ],
        },
    )
    _write_json(
        snapshot_dir / "tushare_snapshot.json",
        {
            "trade_date": "20240402",
            "generated_at": "2024-04-02T09:30:00+08:00",
            "breadth": {"up_count": 2600, "down_count": 2100, "up_pct": 53.0},
            "indices": {"000001.SH": {"name": "SSE", "close": 3100.0, "pct_chg": 0.2}},
            "moneyflow": {"total_net_mf_amount": 1200000.0, "top_entries": []},
            "limit_list": {"up": [{}], "down": []},
        },
    )


def test_build_dashboard_combines_native_and_state_panel(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    snapshot_dir = tmp_path / "snapshots"
    state_panel = tmp_path / "state_panel.csv"
    _write_state_panel(state_panel)
    _write_dashboard_outputs(out_dir)
    _write_dashboard_snapshots(snapshot_dir)

    result = web_dashboard.build_dashboard(
        output_path=tmp_path / "dashboard.html",
        out_dir=out_dir,
        snapshot_dir=snapshot_dir,
        state_panel_path=state_panel,
    )

    assert result.html_path.exists()
    assert result.payload_path is not None and result.payload_path.exists()
    html = result.html_path.read_text(encoding="utf-8")
    assert "市场全景终端" in html
    assert "市场情报看板" in html
    assert "策略实验室" in html
    assert "Macro update" in html
    assert "相似状态后续收益" in html
    assert "Semiconductors" in html
    forbidden = "".join(("lu", "cas"))
    assert forbidden not in html.lower()

    payload = json.loads(result.payload_path.read_text(encoding="utf-8"))
    assert payload["title"] == "市场全景终端"
    assert payload["latest"]["riskAppetite"] == 66.0
    modules = {row["key"]: row["status"] for row in payload["terminal"]["modules"]}
    assert modules["market-sentiment"] == "proxy"
    assert modules["drawdown-levels"] == "proxy"
    assert modules["strategy-lab"] == "missing"
    assert payload["terminal"]["eventItems"][0]["title"] == "Macro update"
    assert payload["terminal"]["eventItems"][0]["sourceChain"][0]["source"] == "Example"
    assert "summary" not in payload["terminal"]["eventItems"][0]
    assert payload["marketIntel"]["themes"][0]["label"] == "AI"
    assert payload["neighbors"], "state-panel rows should produce similar-state neighbors"
    assert payload["neighborSummary"], "forward-return columns should produce analog summary"
    coverage = {row["key"]: row["status"] for row in payload["coverage"]}
    assert coverage["daily_scores"] == "available"
    assert coverage["risk_state"] == "proxy"
    assert coverage["a_share_snapshot"] == "available"


def test_build_dashboard_marks_missing_optional_inputs(tmp_path: Path) -> None:
    result = web_dashboard.build_dashboard(
        output_path=tmp_path / "dashboard.html",
        out_dir=tmp_path / "out",
        snapshot_dir=tmp_path / "snapshots",
    )

    payload_path = result.payload_path
    assert payload_path is not None
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    coverage = {row["key"]: row["status"] for row in payload["coverage"]}
    assert coverage["daily_scores"] == "missing"
    assert coverage["cross_market"] == "missing"
    assert coverage["similar_states"] == "missing"
    assert result.html_path.exists()
