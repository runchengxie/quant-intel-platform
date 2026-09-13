from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from a_share_daily.weekly_client_basket import (
    SourcePosition,
    WeeklyBasketError,
    compose_weekly_basket,
    enrich_source_names,
    filter_source_positions_by_instruments,
    load_cashflow_selection,
    load_dailywatch_family,
    load_microcap_selection,
    write_basket_artifacts,
)


def _position(
    symbol: str,
    strategy: str,
    *,
    rank: int,
    signal_date: str = "20260911",
    valid_until: str | None = "20260918",
) -> SourcePosition:
    return SourcePosition(
        symbol=symbol,
        name=f"Name {symbol}",
        source_strategy=strategy,
        source_product=f"{strategy}.v1",
        signal_date=signal_date,
        valid_until=valid_until,
        rank=rank,
        score=1.0 / rank,
        selection_reason="synthetic fixture",
        artifact_path=f"/tmp/{strategy}.json",
        artifact_sha256="a" * 64,
        research_only=strategy != "dailywatch_family",
        eligible_for_live=strategy == "dailywatch_family",
    )


def _normal_sources(
    *,
    cashflow: list[SourcePosition] | None = None,
    microcap: list[SourcePosition] | None = None,
) -> dict[str, list[SourcePosition]]:
    return {
        "dailywatch_family": [
            _position(f"DW{i:03d}", "dailywatch_family", rank=i) for i in range(1, 6)
        ],
        "cashflow": cashflow
        if cashflow is not None
        else [_position(f"CF{i:03d}", "cashflow", rank=i) for i in range(1, 7)],
        "microcap": microcap
        if microcap is not None
        else [_position(f"MC{i:03d}", "microcap", rank=i) for i in range(1, 5)],
    }


def test_compose_uses_six_cashflow_four_microcap_and_monitors_dailywatch() -> None:
    sources = _normal_sources(
        cashflow=[_position(f"CF{i:03d}", "cashflow", rank=i) for i in range(1, 7)]
    )
    artifact = compose_weekly_basket(sources, as_of_date="20260914")

    assert len(artifact.positions) == 10
    assert {row.source_strategy for row in artifact.positions} == {"cashflow", "microcap"}
    assert len({row.symbol for row in artifact.positions}) == 10
    assert sum(row.source_strategy == "cashflow" for row in artifact.positions) == 6
    assert sum(row.source_strategy == "microcap" for row in artifact.positions) == 4
    assert [row.symbol for row in artifact.monitoring] == [f"DW{i:03d}" for i in range(1, 6)]


def test_cashflow_without_new_rebalance_keeps_original_signal_date() -> None:
    source = _position(
        "CF001",
        "cashflow",
        rank=1,
        signal_date="20260901",
        valid_until="20261231",
    )
    artifact = compose_weekly_basket(
        _normal_sources(
            cashflow=[
                source,
                _position("CF002", "cashflow", rank=2),
                _position("CF003", "cashflow", rank=3),
                _position("CF004", "cashflow", rank=4),
                _position("CF005", "cashflow", rank=5),
                _position("CF006", "cashflow", rank=6),
            ]
        ),
        as_of_date="20260914",
    )

    row = next(row for row in artifact.positions if row.symbol == "CF001")
    assert row.status == "NEW"
    assert row.signal_date == "20260901"
    assert row.valid_until == "20261231"


def test_enrich_source_names_fills_missing_cashflow_name() -> None:
    sources = _normal_sources(microcap=[])
    sources["cashflow"] = [replace(sources["cashflow"][0], name="CF001")]

    enriched = enrich_source_names(sources, {"CF001": "现金流公司"})

    assert enriched["cashflow"][0].name == "现金流公司"
    assert enriched["dailywatch_family"][0].name == "Name DW001"


def test_filter_source_positions_excludes_symbols_not_listed_on_report_date() -> None:
    sources = _normal_sources(microcap=[])
    sources["cashflow"] = [
        _position("DELISTED.SZ", "cashflow", rank=1),
        _position("ACTIVE.SZ", "cashflow", rank=2),
        _position("LATER.SZ", "cashflow", rank=3),
        _position("FUTURE_DELIST.SZ", "cashflow", rank=4),
    ]

    filtered = filter_source_positions_by_instruments(
        sources,
        {
            "DELISTED.SZ": {"list_status": "D", "list_date": "20100101", "delist_date": "20200101"},
            "ACTIVE.SZ": {"list_status": "L", "list_date": "20100101", "delist_date": ""},
            "LATER.SZ": {"list_status": "L", "list_date": "20260915", "delist_date": ""},
            "FUTURE_DELIST.SZ": {
                "list_status": "D",
                "list_date": "20100101",
                "delist_date": "20270101",
            },
        },
        as_of_date="20260914",
    )

    assert [row.symbol for row in filtered["cashflow"]] == ["ACTIVE.SZ", "FUTURE_DELIST.SZ"]


def test_duplicate_symbol_is_replaced_by_same_sleeve_candidate() -> None:
    sources = _normal_sources(
        microcap=[_position(f"MC{i:03d}", "microcap", rank=i) for i in range(1, 6)]
    )
    sources["microcap"][0] = replace(sources["microcap"][0], symbol="CF001")

    artifact = compose_weekly_basket(sources, as_of_date="20260914")

    assert len({row.symbol for row in artifact.positions}) == 10
    assert [row.symbol for row in artifact.positions if row.source_strategy == "microcap"] == [
        "MC002",
        "MC003",
        "MC004",
        "MC005",
    ]


def test_insufficient_candidates_fail_closed() -> None:
    with pytest.raises(WeeklyBasketError, match="10 distinct"):
        compose_weekly_basket(_normal_sources(microcap=[]), as_of_date="20260914")


def test_write_basket_artifacts_creates_canonical_snapshot(tmp_path: Path) -> None:
    artifact = compose_weekly_basket(_normal_sources(), as_of_date="20260914")

    paths = write_basket_artifacts(artifact, tmp_path)

    assert paths["basket"].exists()
    assert paths["receipt"].exists()
    assert paths["latest"].exists()


def _write_json(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_d11_h5_adapter_prefers_four_current_positions(tmp_path: Path) -> None:
    path = _write_json(
        tmp_path / "d11_h5.json",
        {
            "schema_version": "strategy_pipeline.d11_h5_shadow.v2",
            "product_id": "d11_h5_shadow.cn.v2",
            "status": "passed",
            "research_only": True,
            "eligible_for_live": False,
            "source_date": "20260911",
            "signal_date": "20260912",
            "signal": {
                "positions": [
                    {
                        "symbol": f"DW{i:03d}.SZ",
                        "name": f"D{i}",
                        "model_rank": i,
                        "score_percentile": 1 / i,
                    }
                    for i in range(1, 5)
                ]
            },
        },
    )

    rows = load_dailywatch_family(path, as_of_date="20260914")

    assert len(rows) == 4
    assert all(row.source_product == "d11_h5_shadow" for row in rows)
    assert rows[0].signal_date == "20260912"
    assert rows[0].rank == 1
    assert rows[0].score == 1.0


def test_dailywatch20_adapter_accepts_formal_json_array(tmp_path: Path) -> None:
    path = tmp_path / "watchlist_20.json"
    path.write_text(
        json.dumps(
            [
                {
                    "symbol": "300279.SZ",
                    "name": "和晶科技",
                    "rank": 1,
                    "final_score": 1.0,
                    "signal_date": "20260908",
                    "source_date": "20260907",
                }
            ]
        ),
        encoding="utf-8",
    )

    rows = load_dailywatch_family(path, as_of_date="20260914")

    assert len(rows) == 1
    assert rows[0].symbol == "300279.SZ"
    assert rows[0].score == 1.0


def test_cashflow_adapter_rejects_unverified_publication(tmp_path: Path) -> None:
    selection = _write_json(
        tmp_path / "cashflow.json",
        {
            "schema_version": "strategy_app.cashflow.selection.v1",
            "status": "passed",
            "research_only": True,
            "eligible_for_live": False,
            "strategy_id": "cashflow_quality_top50_v1",
            "source_date": "20260901",
            "signal_date": "20260902",
            "targets": [{"symbol": "CF001.SZ", "name": "Cash", "target_weight": 1.0}],
        },
    )
    receipt = _write_json(
        tmp_path / "receipt.json",
        {
            "schema_version": "strategy_pipeline.cashflow.publication.v1",
            "status": "blocked",
            "selection_sha256": hashlib.sha256(selection.read_bytes()).hexdigest(),
        },
    )

    with pytest.raises(WeeklyBasketError, match="publication"):
        load_cashflow_selection(selection, receipt, as_of_date="20260914")


def test_microcap_adapter_requires_explicit_shadow_marker(tmp_path: Path) -> None:
    path = _write_json(
        tmp_path / "microcap.json",
        {
            "schema_version": "microcap.selection.v1",
            "status": "passed",
            "source_date": "20260911",
            "signal_date": "20260912",
            "positions": [{"symbol": "MC001.SZ", "name": "Micro", "rank": 1}],
        },
    )

    with pytest.raises(WeeklyBasketError, match="shadow"):
        load_microcap_selection(path, as_of_date="20260914")


def test_microcap_adapter_requires_research_only_and_three_candidates(tmp_path: Path) -> None:
    path = _write_json(
        tmp_path / "microcap.json",
        {
            "schema_version": "microcap.selection.v1",
            "status": "passed",
            "shadow": True,
            "research_only": False,
            "eligible_for_live": True,
            "signal_date": "20260911",
            "positions": [
                {"symbol": "MC001.SZ", "name": "Micro", "rank": 1},
                {"symbol": "MC002.SZ", "name": "Micro 2", "rank": 2},
            ],
        },
    )

    with pytest.raises(WeeklyBasketError, match="research-only"):
        load_microcap_selection(path, as_of_date="20260914")


def test_microcap_adapter_preserves_shadow_positions(tmp_path: Path) -> None:
    path = _write_json(
        tmp_path / "microcap.json",
        {
            "schema_version": "microcap.selection.v1",
            "status": "passed",
            "shadow": True,
            "research_only": True,
            "eligible_for_live": False,
            "signal_date": "20260911",
            "positions": [
                {"symbol": "MC001.SZ", "name": "Micro", "rank": 1, "score": 0.9},
                {"symbol": "MC002.SZ", "name": "Micro 2", "rank": 2, "score": 0.8},
                {"symbol": "MC003.SZ", "name": "Micro 3", "rank": 3, "score": 0.7},
            ],
        },
    )

    rows = load_microcap_selection(path, as_of_date="20260914")

    assert [row.symbol for row in rows] == ["MC001.SZ", "MC002.SZ", "MC003.SZ"]
    assert all(row.research_only for row in rows)
    assert all(not row.eligible_for_live for row in rows)
