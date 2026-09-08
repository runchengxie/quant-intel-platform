from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pandas as pd
import pytest
from _daily_watch20_candidate_test_utils import (
    strict_v2_policy_id,
    strict_v3_policy_id,
    v2_candidate_pool,
    v3_candidate_pool,
    write_v2_source,
)
from test_daily_watch20 import (
    _rewrite_v2_policy_identity,
    _write_v2_artifact,
)

from a_share_daily import cli
from a_share_daily.daily_watch20 import (
    DailyWatch20ValidationError,
    build_daily_watch20_html,
    load_daily_watch20,
)
from a_share_daily.daily_watch20_client_render import _client_candidate_data_warning
from a_share_daily.daily_watch20_render import render_daily_watch20_markdown


def _write_sparse_v2_artifact(
    root: Path,
    *,
    missing_ranks: tuple[int, ...] = (53,),
) -> Path:
    _write_v2_artifact(root)
    data_path = root / "watchlist_20.csv"
    frame = pd.read_csv(data_path)
    frame["ths_hot_rank"] = [*range(1, 20), 54]
    frame.to_csv(data_path, index=False)
    source_path = write_v2_source(root, frame, missing_ranks=missing_ranks)
    receipt_path = root / "selection_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["candidate_pool"] = v2_candidate_pool(
        source_path,
        missing_ranks=missing_ranks,
    )
    receipt["input_freshness"]["candidate_pool_symbols"] = 100 - len(missing_ranks)
    receipt["strategy_policy"]["candidate_pool"].update(
        {
            "mode": "ths_hot_strict_v2",
            "policy_id": strict_v2_policy_id(),
        }
    )
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf-8")
    _rewrite_v2_policy_identity(root)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["candidate_pool"] = v2_candidate_pool(
        source_path,
        missing_ranks=missing_ranks,
    )
    receipt["artifacts"]["watchlist_20.csv"]["sha256"] = hashlib.sha256(
        data_path.read_bytes()
    ).hexdigest()
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf-8")
    return root


def _write_sparse_v3_artifact(
    root: Path,
    *,
    missing_ranks: tuple[int, ...] = (19,),
) -> Path:
    _write_v2_artifact(root)
    data_path = root / "watchlist_20.csv"
    frame = pd.read_csv(data_path)
    frame["ths_hot_rank"] = [*range(1, 19), 20, 21]
    frame.to_csv(data_path, index=False)
    source_path = write_v2_source(root, frame, missing_ranks=missing_ranks)
    receipt_path = root / "selection_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["candidate_pool"] = v3_candidate_pool(
        source_path,
        missing_ranks=missing_ranks,
    )
    receipt["input_freshness"].update(
        {
            "candidate_pool_mode": "ths_hot_strict_v3",
            "candidate_pool_policy_id": strict_v3_policy_id(),
            "candidate_pool_symbols": 100 - len(missing_ranks),
        }
    )
    receipt["strategy_policy"]["candidate_pool"].update(
        {
            "mode": "ths_hot_strict_v3",
            "policy_id": strict_v3_policy_id(),
        }
    )
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf-8")
    _rewrite_v2_policy_identity(root)
    return root


def _rewrite_watchlist_hash(root: Path, frame: pd.DataFrame) -> None:
    data_path = root / "watchlist_20.csv"
    frame.to_csv(data_path, index=False)
    receipt_path = root / "selection_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["artifacts"]["watchlist_20.csv"]["sha256"] = hashlib.sha256(
        data_path.read_bytes()
    ).hexdigest()
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf-8")


def _rewrite_source(root: Path, source: pd.DataFrame) -> None:
    source_path = root / "ths-hot" / "data" / "trade_date=20260710" / "part.parquet"
    source.to_parquet(source_path, index=False)
    receipt_path = root / "selection_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["candidate_pool"]["raw_rows"] = len(source)
    receipt["candidate_pool"]["files"][0]["sha256"] = hashlib.sha256(
        source_path.read_bytes()
    ).hexdigest()
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf-8")


def test_load_accepts_one_post_top20_rank_gap_without_renumbering(tmp_path: Path) -> None:
    root = _write_sparse_v2_artifact(tmp_path / "latest")

    artifact = load_daily_watch20(root, expected_candidate_pool_mode="ths_hot_strict_v2")

    candidate_pool = artifact.receipt["candidate_pool"]
    assert candidate_pool["missing_ranks"] == [53]
    assert candidate_pool["max_missing_ranks"] == 2
    assert candidate_pool["rank_coverage_status"] == "degraded"
    assert artifact.frame["ths_hot_rank"].max() == 54
    assert 53 not in set(artifact.frame["ths_hot_rank"])


def test_load_v3_accepts_rank_19_gap_without_renumbering(tmp_path: Path) -> None:
    root = _write_sparse_v3_artifact(tmp_path / "latest")

    artifact = load_daily_watch20(root, expected_candidate_pool_mode="ths_hot_strict_v3")

    candidate_pool = artifact.receipt["candidate_pool"]
    assert candidate_pool["missing_ranks"] == [19]
    assert candidate_pool["required_top_ranks"] == 1
    assert candidate_pool["rank_coverage_status"] == "degraded"
    assert 19 not in set(artifact.frame["ths_hot_rank"])
    assert 20 in set(artifact.frame["ths_hot_rank"])


def test_client_cli_defaults_to_strict_v3(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _write_sparse_v3_artifact(tmp_path / "latest")
    output = tmp_path / "should-not-exist"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "a-share-daily",
            "daily-watch20",
            "--root",
            str(root),
            "--out-dir",
            str(output),
            "--dry-run",
        ],
    )

    cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "passed"
    assert not output.exists()


def test_load_v3_rejects_missing_rank_one(tmp_path: Path) -> None:
    root = _write_sparse_v3_artifact(tmp_path / "latest")
    receipt_path = root / "selection_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["candidate_pool"]["missing_ranks"] = [1]
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(DailyWatch20ValidationError, match="missing a required top rank"):
        load_daily_watch20(root, expected_candidate_pool_mode="ths_hot_strict_v3")


def test_load_v2_still_rejects_rank_19_gap(tmp_path: Path) -> None:
    root = _write_sparse_v2_artifact(tmp_path / "latest", missing_ranks=(19,))

    with pytest.raises(DailyWatch20ValidationError, match="missing a required top rank"):
        load_daily_watch20(root, expected_candidate_pool_mode="ths_hot_strict_v2")


def test_load_accepts_two_post_top20_rank_gaps_and_warns_client(tmp_path: Path) -> None:
    root = _write_sparse_v2_artifact(
        tmp_path / "latest",
        missing_ranks=(53, 72),
    )

    artifact = load_daily_watch20(root, expected_candidate_pool_mode="ths_hot_strict_v2")
    warning = _client_candidate_data_warning(artifact.receipt)
    markdown = render_daily_watch20_markdown(artifact, audience="client")
    document = build_daily_watch20_html(artifact, audience="client")

    assert artifact.receipt["candidate_pool"]["missing_ranks"] == [53, 72]
    assert "TuShare 数据服务商疑似缺失部分热榜数据" in warning
    assert "排名 53、72" in warning
    assert warning in markdown
    assert warning in document


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda candidate: candidate.update(missing_ranks=[53, 54, 55]),
            "too many missing ranks",
        ),
        (
            lambda candidate: candidate.update(missing_ranks=[20]),
            "missing a required top rank",
        ),
        (
            lambda candidate: candidate.update(rank_coverage_status="complete"),
            "rank_coverage_status contradicts missing_ranks",
        ),
        (lambda candidate: candidate.update(rank_ties=1), "rank_ties must be zero"),
        (
            lambda candidate: candidate.update(snapshot_rows=100),
            "snapshot row evidence is not conserved",
        ),
        (
            lambda candidate: candidate.update(component_span_seconds=181),
            "component time range is invalid",
        ),
        (
            lambda candidate: candidate.update(latest_observed_minute="2026-07-10 16:29"),
            "latest_observed_minute does not match the latest source snapshot",
        ),
        (
            lambda candidate: candidate.update(skipped_incomplete_snapshots=1),
            "skipped_incomplete_snapshots does not match the latest source snapshot",
        ),
    ],
)
def test_load_rejects_tampered_sparse_v2_evidence(
    tmp_path: Path,
    mutation: Callable[[dict[str, object]], object],
    message: str,
) -> None:
    root = _write_sparse_v2_artifact(tmp_path / "latest")
    receipt_path = root / "selection_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    candidate_pool = cast(dict[str, object], receipt["candidate_pool"])
    mutation(candidate_pool)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(DailyWatch20ValidationError, match=message):
        load_daily_watch20(root, expected_candidate_pool_mode="ths_hot_strict_v2")


def test_load_rejects_selected_rank_renumbering(tmp_path: Path) -> None:
    root = _write_sparse_v2_artifact(tmp_path / "latest")
    frame = pd.read_csv(root / "watchlist_20.csv")
    frame.loc[frame["ths_hot_rank"].eq(54), "ths_hot_rank"] = 52
    _rewrite_watchlist_hash(root, frame)

    with pytest.raises(DailyWatch20ValidationError, match="do not preserve source rank"):
        load_daily_watch20(root, expected_candidate_pool_mode="ths_hot_strict_v2")


def test_load_rejects_selection_of_a_missing_rank(tmp_path: Path) -> None:
    root = _write_sparse_v2_artifact(tmp_path / "latest")
    frame = pd.read_csv(root / "watchlist_20.csv")
    frame.loc[frame["ths_hot_rank"].eq(54), "ths_hot_rank"] = 53
    _rewrite_watchlist_hash(root, frame)

    with pytest.raises(DailyWatch20ValidationError, match="contradict missing-rank evidence"):
        load_daily_watch20(root, expected_candidate_pool_mode="ths_hot_strict_v2")


def test_load_rejects_self_consistent_but_earlier_source_component(tmp_path: Path) -> None:
    root = _write_v2_artifact(tmp_path / "latest")
    source_path = root / "ths-hot" / "data" / "trade_date=20260710" / "part.parquet"
    earlier = pd.read_parquet(source_path)
    later = earlier.copy()
    later["rank_time"] = "2026-07-10 16:31:00"
    _rewrite_source(root, pd.concat([earlier, later], ignore_index=True))

    with pytest.raises(DailyWatch20ValidationError, match="latest source snapshot"):
        load_daily_watch20(root, expected_candidate_pool_mode="ths_hot_strict_v2")


def test_load_rejects_source_snapshot_before_close_cutoff(tmp_path: Path) -> None:
    root = _write_v2_artifact(tmp_path / "latest")
    source_path = root / "ths-hot" / "data" / "trade_date=20260710" / "part.parquet"
    source = pd.read_parquet(source_path)
    source["rank_time"] = "2026-07-10 14:59:59"
    _rewrite_source(root, source)

    with pytest.raises(DailyWatch20ValidationError, match="no qualifying close snapshot"):
        load_daily_watch20(root, expected_candidate_pool_mode="ths_hot_strict_v2")


def test_load_rejects_snapshot_over_fallback_age(tmp_path: Path) -> None:
    root = _write_v2_artifact(tmp_path / "latest")
    source_path = root / "ths-hot" / "data" / "trade_date=20260710" / "part.parquet"
    source = pd.read_parquet(source_path)
    incomplete_later = source.iloc[[0]].copy()
    incomplete_later["symbol"] = "603999.SH"
    incomplete_later["rank"] = 1
    incomplete_later["rank_time"] = "2026-07-10 17:31:00"
    _rewrite_source(root, pd.concat([source, incomplete_later], ignore_index=True))

    with pytest.raises(DailyWatch20ValidationError, match="too far behind the latest row"):
        load_daily_watch20(root, expected_candidate_pool_mode="ths_hot_strict_v2")


def test_load_uses_producer_second_precision_for_source_rank_time(tmp_path: Path) -> None:
    root = _write_v2_artifact(tmp_path / "latest")
    source_path = root / "ths-hot" / "data" / "trade_date=20260710" / "part.parquet"
    source = pd.read_parquet(source_path)
    source["rank_time"] = "2026-07-10 16:30:00.500000"
    _rewrite_source(root, source)

    artifact = load_daily_watch20(root, expected_candidate_pool_mode="ths_hot_strict_v2")

    assert len(artifact.frame) == 20


def test_load_rejects_non_finite_source_rank_as_validation_error(tmp_path: Path) -> None:
    root = _write_v2_artifact(tmp_path / "latest")
    source_path = root / "ths-hot" / "data" / "trade_date=20260710" / "part.parquet"
    source = pd.read_parquet(source_path)
    source["rank"] = source["rank"].astype(float)
    source.loc[0, "rank"] = float("inf")
    _rewrite_source(root, source)

    with pytest.raises(DailyWatch20ValidationError, match="invalid ranks"):
        load_daily_watch20(root, expected_candidate_pool_mode="ths_hot_strict_v2")


def test_load_reassembles_valid_cross_minute_batch_fallback(tmp_path: Path) -> None:
    root = _write_sparse_v2_artifact(tmp_path / "latest")
    source_path = root / "ths-hot" / "data" / "trade_date=20260710" / "part.parquet"
    source = pd.read_parquet(source_path).sort_values("rank").reset_index(drop=True)
    source["rank_time"] = pd.date_range(
        "2026-07-10 16:30:00",
        periods=len(source),
        freq="s",
    )
    _rewrite_source(root, source)

    receipt_path = root / "selection_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    candidate = receipt["candidate_pool"]
    candidate.update(
        {
            "assembly_path": "batch_fallback",
            "snapshot_minute": "2026-07-10 16:31",
            "latest_observed_minute": "2026-07-10 16:31",
            "snapshot_time_min": "2026-07-10 16:30:00",
            "snapshot_time_max": "2026-07-10 16:31:38",
            "component_time_start": "2026-07-10 16:30:00",
            "component_time_end": "2026-07-10 16:31:38",
            "component_span_seconds": 98,
        }
    )
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf-8")

    frame = pd.read_csv(root / "watchlist_20.csv")
    source_times = source.set_index("symbol")["rank_time"].astype(str)
    frame["ths_hot_rank_time"] = frame["symbol"].map(source_times)
    _rewrite_watchlist_hash(root, frame)

    artifact = load_daily_watch20(root, expected_candidate_pool_mode="ths_hot_strict_v2")

    assert artifact.receipt["candidate_pool"]["assembly_path"] == "batch_fallback"
    assert artifact.frame["ths_hot_rank"].max() == 54


def test_load_rejects_missing_v2_input_freshness(tmp_path: Path) -> None:
    root = _write_v2_artifact(tmp_path / "latest")
    receipt_path = root / "selection_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt.pop("input_freshness")
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(DailyWatch20ValidationError, match="input_freshness is required"):
        load_daily_watch20(root, expected_candidate_pool_mode="ths_hot_strict_v2")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("status", "stale", "status must be ready"),
        ("require_current", False, "require_current must be true"),
        ("reasons", ["stale"], "reasons must be empty"),
        ("source_date", "20260709", "source_date must be 20260710"),
        ("signal_date", "20260714", "signal_date must be 20260713"),
        ("daily_as_of", "20260709", "daily_as_of must be 20260710"),
        (
            "candidate_pool_mode",
            "ths_hot_strict",
            "candidate_pool_mode must be ths_hot_strict_v2",
        ),
        ("candidate_pool_policy_id", "tampered", "candidate_pool_policy_id mismatch"),
        ("candidate_pool_symbols", 99, "candidate_pool_symbols mismatch"),
        (
            "required_minute_date",
            "20260709",
            "required_minute_date mismatch minute_features.required_date",
        ),
        ("minute_source", "legacy", "minute_source is invalid"),
    ],
)
def test_load_rejects_tampered_v2_input_freshness(
    tmp_path: Path,
    field: str,
    value: object,
    message: str,
) -> None:
    root = _write_v2_artifact(tmp_path / "latest")
    receipt_path = root / "selection_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["input_freshness"][field] = value
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(DailyWatch20ValidationError, match=message):
        load_daily_watch20(root, expected_candidate_pool_mode="ths_hot_strict_v2")


def test_client_rejects_strict_v2_schema_downgrade(tmp_path: Path) -> None:
    root = _write_sparse_v2_artifact(tmp_path / "latest")
    receipt_path = root / "selection_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["schema_version"] = "daily_watch20.selection.v1"
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(DailyWatch20ValidationError, match="requires daily_watch20.selection.v2"):
        load_daily_watch20(root, expected_candidate_pool_mode="ths_hot_strict_v2")


def test_internal_consumer_accepts_research_v2_all_market_without_freshness(
    tmp_path: Path,
) -> None:
    root = _write_v2_artifact(tmp_path / "latest")
    receipt_path = root / "selection_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt.pop("input_freshness")
    receipt["publication_tier"] = "research"
    receipt["candidate_pool"] = {
        "mode": "all_market",
        "policy_id": "daily_watch20.all_market.v1",
    }
    receipt["strategy_policy"]["candidate_pool"] = {
        "mode": "all_market",
        "policy_id": "daily_watch20.all_market.v1",
        "restricted": False,
        "fail_closed": False,
        "positive_change_only": False,
        "min_symbols": None,
        "snapshot_min_symbols": None,
    }
    receipt["strategy_policy"]["safety"]["publication_tier"] = "research"
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf-8")
    _rewrite_v2_policy_identity(root)

    artifact = load_daily_watch20(root)

    assert artifact.receipt["publication_tier"] == "research"
    assert artifact.receipt["candidate_pool"]["mode"] == "all_market"
