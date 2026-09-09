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
        else [_position(f"CF{i:03d}", "cashflow", rank=i) for i in range(1, 5)],
        "microcap": microcap
        if microcap is not None
        else [_position(f"MC{i:03d}", "microcap", rank=i) for i in range(1, 5)],
    }


def test_compose_uses_four_dailywatch_three_cashflow_three_microcap() -> None:
    artifact = compose_weekly_basket(_normal_sources(), as_of_date="20260914")

    assert len(artifact.positions) == 10
    assert {row.source_strategy for row in artifact.positions} == {
        "dailywatch_family",
        "cashflow",
        "microcap",
    }
    assert len({row.symbol for row in artifact.positions}) == 10
    assert sum(row.source_strategy == "dailywatch_family" for row in artifact.positions) == 4
    assert sum(row.source_strategy == "cashflow" for row in artifact.positions) == 3
    assert sum(row.source_strategy == "microcap" for row in artifact.positions) == 3


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
            ]
        ),
        as_of_date="20260914",
    )

    row = next(row for row in artifact.positions if row.symbol == "CF001")
    assert row.status == "NEW"
    assert row.signal_date == "20260901"
    assert row.valid_until == "20261231"


def test_duplicate_symbol_is_replaced_by_same_sleeve_candidate() -> None:
    sources = _normal_sources()
    sources["cashflow"][0] = replace(sources["cashflow"][0], symbol="DW001")

    artifact = compose_weekly_basket(sources, as_of_date="20260914")

    assert len({row.symbol for row in artifact.positions}) == 10
    assert [row.symbol for row in artifact.positions if row.source_strategy == "cashflow"] == [
        "CF002",
        "CF003",
        "CF004",
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
