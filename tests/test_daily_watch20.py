from __future__ import annotations

import hashlib
import json
import struct
import sys
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pandas as pd
import pytest
from _daily_watch20_candidate_test_utils import (
    strict_v2_policy_id as _strict_v2_policy_id,
)
from _daily_watch20_candidate_test_utils import v2_candidate_pool as _v2_candidate_pool
from _daily_watch20_candidate_test_utils import write_v2_source as _write_v2_source
from _daily_watch20_policy_test_utils import build_valid_v2_policy
from matplotlib import image as mpimg

from a_share_daily import cli
from a_share_daily.daily_watch20 import (
    DailyWatch20ValidationError,
    artifact_summary,
    build_daily_watch20_html,
    load_daily_watch20,
)
from a_share_daily.daily_watch20_client_render import (
    CLIENT_METHOD_SUMMARY,
    _client_table_display_budget,
    _display_width,
    _png_reason_risk_text,
    generate_daily_watch20_client_png,
)
from a_share_daily.daily_watch20_light_render import _light_overview, _light_stock_row_copy
from a_share_daily.daily_watch20_render import (
    render_daily_watch20,
    render_daily_watch20_markdown,
)


def _watchlist_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index in range(20):
        sleeve = "A" if index < 4 else "B"
        rank = index + 1 if sleeve == "A" else index - 3
        symbol = f"600{index:03d}.SH" if index % 2 == 0 else f"000{index:03d}.SZ"
        rows.append(
            {
                "signal_date": "20260713",
                "source_date": "20260710",
                "symbol": symbol,
                "name": f"样本{index + 1}",
                "sleeve": sleeve,
                "rank": rank,
                "tracking_weight": 0.1 if sleeve == "A" else 0.0375,
                "xgb_score": 0.8 - index * 0.01,
                "xgb_percentile": 0.99 - index * 0.01,
                "guard_score": 0.7,
                "final_score": 0.85 - index * 0.01,
                "industry": ("半导体" if index % 3 == 0 else "电子元件"),
                "theme": ("AI算力硬件" if index % 2 == 0 else "稳健补充"),
                "dual_confirmed": index % 2 == 0,
                "is_new": index in {0, 5},
                "top_drivers": "盈利动量|量价确认" if index % 2 == 0 else "低波收敛|流动性",
                "primary_risk": "高波动" if sleeve == "A" else "收益弹性有限",
                "model_version": "DailyWatch20-XGB-v1",
                "feature_set_id": "daily_watch20_v1",
                "data_as_of": "20260710",
            }
        )
    return rows


def _receipt() -> dict[str, object]:
    return {
        "schema_version": "daily_watch20.selection.v1",
        "status": "passed",
        "source_date": "20260710",
        "signal_date": "20260713",
        "generated_at": "2026-07-10T18:00:00+08:00",
        "model_version": "DailyWatch20-XGB-v1",
        "feature_set_id": "daily_watch20_v1",
        "market_scope": "sh-sz",
        "counts": {"total": 20, "a": 4, "b": 16, "unique": 20},
        "tracking_weight_sum": 1.0,
        "minute_features": {
            "enabled": True,
            "as_of": "20260710",
            "required_date": "20260710",
            "lag_trade_days": 0,
        },
        "regime": {"label": "平衡偏进攻", "summary": "量能正常，控制追高风险"},
    }


def _write_artifact(root: Path) -> Path:
    root.mkdir(parents=True)
    calendar_path = root / "trade_cal.parquet"
    pd.DataFrame(
        {
            "cal_date": ["20260709", "20260710", "20260711", "20260712", "20260713"],
            "is_open": [1, 1, 0, 0, 1],
        }
    ).to_parquet(calendar_path)
    data_path = root / "watchlist_20.csv"
    pd.DataFrame(_watchlist_rows()).to_csv(data_path, index=False)
    receipt = _receipt()
    receipt["inputs"] = {"trade_cal": str(calendar_path)}
    receipt["artifacts"] = {
        "watchlist_20.csv": {
            "path": "watchlist_20.csv",
            "sha256": hashlib.sha256(data_path.read_bytes()).hexdigest(),
        }
    }
    (root / "selection_receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False),
        encoding="utf-8",
    )
    return root


def _write_strict_ths_artifact(root: Path) -> Path:
    _write_artifact(root)
    data_path = root / "watchlist_20.csv"
    frame = pd.read_csv(data_path)
    frame["ths_hot_rank"] = range(1, 21)
    frame["ths_hot_pct_change"] = [1.0] * 20
    frame["ths_hot_rank_time"] = ["2026-07-10 16:30:00"] * 20
    frame.to_csv(data_path, index=False)
    receipt_path = root / "selection_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["candidate_pool"] = {
        "mode": "ths_hot_strict",
        "policy_id": (
            "daily_watch20.ths_hot_positive_close.v1:min_symbols=20:"
            "snapshot_min_symbols=80:close_cutoff_minute=900:"
            "max_snapshot_fallback_minutes=60"
        ),
        "source": "tushare.ths_hot",
        "root": str(root / "ths-hot"),
        "source_date": "20260710",
        "restricted": True,
        "fail_closed": True,
        "positive_change_only": True,
        "min_symbols": 20,
        "snapshot_min_symbols": 80,
        "close_cutoff_minute": 900,
        "max_snapshot_fallback_minutes": 60,
        "snapshot_unique_symbols": 100,
        "pool_symbols": 40,
        "eligible_intersection_symbols": 35,
    }
    receipt["construction"] = {"selected_outside_candidate_pool": 0}
    receipt["artifacts"]["watchlist_20.csv"]["sha256"] = hashlib.sha256(
        data_path.read_bytes()
    ).hexdigest()
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf-8")
    return root


def _policy_id(policy: dict[str, object]) -> str:
    canonical = json.dumps(
        policy,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return "daily_watch20.strategy_policy.v1:sha256:" + hashlib.sha256(canonical).hexdigest()


def _write_v2_artifact(root: Path) -> Path:
    _write_strict_ths_artifact(root)
    receipt_path = root / "selection_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    data_path = root / "watchlist_20.csv"
    frame = pd.read_csv(data_path)
    source_path = _write_v2_source(root, frame)
    receipt["candidate_pool"] = _v2_candidate_pool(source_path, missing_ranks=())
    receipt["input_freshness"] = {
        "status": "ready",
        "require_current": True,
        "reasons": [],
        "source_date": "20260710",
        "signal_date": "20260713",
        "daily_as_of": "20260710",
        "required_minute_date": "20260710",
        "minute_source": "canonical",
        "canonical_minute_date_max": "20260710",
        "candidate_pool_mode": "ths_hot_strict_v2",
        "candidate_pool_policy_id": _strict_v2_policy_id(),
        "candidate_pool_symbols": 100,
    }
    policy = build_valid_v2_policy(receipt)
    policy_id = _policy_id(policy)
    features = cast(dict[str, object], policy["features"])
    feature_set_id = str(features["feature_set_id"])
    model_version = "DailyWatch20-XGB4-Guarded16-v2:test-fixture"
    receipt.update(
        {
            "schema_version": "daily_watch20.selection.v2",
            "strategy_policy": policy,
            "strategy_policy_id": policy_id,
            "publication_tier": "production",
            "eligible_for_live": False,
            "feature_set_id": feature_set_id,
            "model_version": model_version,
        }
    )
    frame["strategy_policy_id"] = policy_id
    frame["feature_set_id"] = feature_set_id
    frame["model_version"] = model_version
    frame.to_csv(data_path, index=False)
    receipt["artifacts"]["watchlist_20.csv"]["sha256"] = hashlib.sha256(
        data_path.read_bytes()
    ).hexdigest()
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf-8")
    return root


def _rewrite_v2_policy_identity(root: Path) -> None:
    receipt_path = root / "selection_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    policy_id = _policy_id(receipt["strategy_policy"])
    receipt["strategy_policy_id"] = policy_id
    data_path = root / "watchlist_20.csv"
    frame = pd.read_csv(data_path)
    frame["strategy_policy_id"] = policy_id
    frame.to_csv(data_path, index=False)
    receipt["artifacts"]["watchlist_20.csv"]["sha256"] = hashlib.sha256(
        data_path.read_bytes()
    ).hexdigest()
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf-8")


def _section(payload: dict[str, object], name: str) -> dict[str, object]:
    value = payload[name]
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def test_load_daily_watch20_validates_and_normalizes_contract(tmp_path: Path) -> None:
    root = _write_artifact(tmp_path / "latest")

    artifact = load_daily_watch20(root, expected_source_date="2026-07-10")

    assert artifact.source_date == "20260710"
    assert artifact.signal_date == "20260713"
    assert len(artifact.a_frame) == 4
    assert len(artifact.b_frame) == 16
    assert artifact.frame["symbol"].nunique() == 20
    assert artifact.frame["tracking_weight"].sum() == pytest.approx(1.0)


def test_load_daily_watch20_accepts_strict_v2_and_reports_actual_schema(tmp_path: Path) -> None:
    root = _write_v2_artifact(tmp_path / "latest")

    artifact = load_daily_watch20(root, expected_candidate_pool_mode="ths_hot_strict_v2")

    assert artifact.receipt["schema_version"] == "daily_watch20.selection.v2"
    assert artifact_summary(artifact)["schema_version"] == "daily_watch20.selection.v2"
    assert set(artifact.frame["strategy_policy_id"]) == {artifact.receipt["strategy_policy_id"]}


def test_load_daily_watch20_rejects_unknown_schema(tmp_path: Path) -> None:
    root = _write_artifact(tmp_path / "latest")
    receipt_path = root / "selection_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["schema_version"] = "daily_watch20.selection.v3"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    with pytest.raises(DailyWatch20ValidationError, match="schema_version must be one of"):
        load_daily_watch20(root)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (
            "strategy_policy_id",
            "daily_watch20.strategy_policy.v1:sha256:" + "0" * 64,
            "does not match strategy_policy",
        ),
        (
            "publication_tier",
            "preview",
            "publication_tier must be production or research",
        ),
        ("eligible_for_live", True, "eligible_for_live must be false"),
    ],
)
def test_load_daily_watch20_rejects_invalid_v2_receipt_carriers(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    root = _write_v2_artifact(tmp_path / "latest")
    receipt_path = root / "selection_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt[field] = value
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    with pytest.raises(DailyWatch20ValidationError, match=message):
        load_daily_watch20(root)


@pytest.mark.parametrize(
    ("section", "field", "value", "message"),
    [
        (None, "feature_set_id", "wrong-features", "feature_set_id does not match"),
        ("candidate_pool", "mode", "unrestricted", "candidate_pool mode does not match"),
        ("candidate_pool", "policy_id", "wrong-policy", "candidate_pool policy_id does not match"),
        (None, "market_scope", "us", "receipt.market_scope must be sh-sz"),
    ],
)
def test_load_daily_watch20_rejects_v2_policy_carrier_mismatch(
    tmp_path: Path, section: str | None, field: str, value: object, message: str
) -> None:
    root = _write_v2_artifact(tmp_path / "latest")
    receipt_path = root / "selection_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    carrier = receipt if section is None else receipt[section]
    assert isinstance(carrier, dict)
    carrier[field] = value
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    with pytest.raises(DailyWatch20ValidationError, match=message):
        load_daily_watch20(root)


def test_load_daily_watch20_rejects_v2_row_policy_id_mismatch(tmp_path: Path) -> None:
    root = _write_v2_artifact(tmp_path / "latest")
    data_path = root / "watchlist_20.csv"
    frame = pd.read_csv(data_path)
    frame.loc[0, "strategy_policy_id"] = "daily_watch20.strategy_policy.v1:sha256:" + "f" * 64
    frame.to_csv(data_path, index=False)
    receipt_path = root / "selection_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["artifacts"]["watchlist_20.csv"]["sha256"] = hashlib.sha256(
        data_path.read_bytes()
    ).hexdigest()
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    with pytest.raises(DailyWatch20ValidationError, match="row strategy_policy_id"):
        load_daily_watch20(root)


def test_load_daily_watch20_rejects_v2_without_policy_or_row_carrier(tmp_path: Path) -> None:
    missing_policy = _write_v2_artifact(tmp_path / "missing-policy")
    receipt_path = missing_policy / "selection_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt.pop("strategy_policy")
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(DailyWatch20ValidationError, match="strategy_policy must be a mapping"):
        load_daily_watch20(missing_policy)

    missing_row_carrier = _write_v2_artifact(tmp_path / "missing-row-carrier")
    data_path = missing_row_carrier / "watchlist_20.csv"
    frame = pd.read_csv(data_path).drop(columns=["strategy_policy_id"])
    frame.to_csv(data_path, index=False)
    receipt_path = missing_row_carrier / "selection_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["artifacts"]["watchlist_20.csv"]["sha256"] = hashlib.sha256(
        data_path.read_bytes()
    ).hexdigest()
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(DailyWatch20ValidationError, match="strategy_policy_id"):
        load_daily_watch20(missing_row_carrier)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda policy: policy.pop("news_heat"), "missing required sections"),
        (lambda policy: _section(policy, "model").clear(), "model must not be empty"),
        (
            lambda policy: _section(policy, "model").__setitem__("type", "linear_model"),
            "must be one of",
        ),
        (
            lambda policy: _section(_section(policy, "model"), "params").__setitem__(
                "learning_rate", 0.0
            ),
            "must be > 0.0",
        ),
        (
            lambda policy: _section(policy, "features").__setitem__(
                "minute_feature_schema", "daily_watch20.minute_features.v1"
            ),
            "minute_feature_schema must be daily_watch20.minute_features.v3",
        ),
        (
            lambda policy: _section(policy, "label").__setitem__("entry_time", "source close"),
            "entry_time must be next trade day open",
        ),
        (
            lambda policy: _section(policy, "candidate_pool").__setitem__("restricted", False),
            "restricted and fail_closed must match",
        ),
        (
            lambda policy: _section(policy, "candidate_pool").pop("max_missing_ranks"),
            "missing required fields.*max_missing_ranks",
        ),
        (
            lambda policy: _section(policy, "candidate_pool").__setitem__("max_missing_ranks", 1),
            "max_missing_ranks must be 2",
        ),
        (
            lambda policy: _section(policy, "candidate_pool").update(
                {
                    "mode": "ths_hot_strict",
                    "policy_id": (
                        "daily_watch20.ths_hot_positive_close.v1:min_symbols=20:"
                        "snapshot_min_symbols=80:close_cutoff_minute=900:"
                        "max_snapshot_fallback_minutes=60"
                    ),
                }
            ),
            "max_missing_ranks is only valid in sparse strict candidate-pool modes",
        ),
        (
            lambda policy: _section(policy, "news_heat").__setitem__("effective_enabled", True),
            "cannot be true when configured_enabled=false",
        ),
        (
            lambda policy: _section(policy, "construction").__setitem__("guard_weight", 0.3),
            "ml_weight and guard_weight must sum to 1",
        ),
        (
            lambda policy: _section(policy, "safety").__setitem__(
                "publication_window_end_exclusive", "09:30:00"
            ),
            "must be 09:15:00",
        ),
        (
            lambda policy: _section(policy, "construction").__setitem__("date_col", "signal_date"),
            "must match features.date_col",
        ),
    ],
)
def test_load_daily_watch20_rejects_rehashed_but_semantically_invalid_v2_policy(
    tmp_path: Path, mutation: Callable[[dict[str, object]], object], message: str
) -> None:
    root = _write_v2_artifact(tmp_path / "latest")
    receipt_path = root / "selection_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    policy = cast(dict[str, object], receipt["strategy_policy"])
    mutation(policy)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf-8")
    _rewrite_v2_policy_identity(root)

    with pytest.raises(DailyWatch20ValidationError, match=message):
        load_daily_watch20(root)


def test_load_daily_watch20_enforces_strict_ths_hot_client_contract(tmp_path: Path) -> None:
    root = _write_strict_ths_artifact(tmp_path / "latest")

    artifact = load_daily_watch20(root, expected_candidate_pool_mode="ths_hot_strict")

    assert artifact.frame["ths_hot_pct_change"].gt(0).all()

    receipt_path = root / "selection_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["construction"] = {}
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(DailyWatch20ValidationError, match="selected_outside_candidate_pool"):
        load_daily_watch20(root, expected_candidate_pool_mode="ths_hot_strict")


def test_load_daily_watch20_rejects_invalid_strict_policy_and_infinite_change(
    tmp_path: Path,
) -> None:
    root = _write_strict_ths_artifact(tmp_path / "latest")
    receipt_path = root / "selection_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["candidate_pool"]["policy_id"] = "daily_watch20.ths_hot_positive_close.v1:garbage"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(DailyWatch20ValidationError, match="policy_id"):
        load_daily_watch20(root, expected_candidate_pool_mode="ths_hot_strict")

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["candidate_pool"]["policy_id"] = (
        "daily_watch20.ths_hot_positive_close.v1:min_symbols=20:"
        "snapshot_min_symbols=80:close_cutoff_minute=900:"
        "max_snapshot_fallback_minutes=60"
    )
    data_path = root / "watchlist_20.csv"
    frame = pd.read_csv(data_path)
    frame.loc[0, "ths_hot_pct_change"] = float("inf")
    frame.to_csv(data_path, index=False)
    receipt["artifacts"]["watchlist_20.csv"]["sha256"] = hashlib.sha256(
        data_path.read_bytes()
    ).hexdigest()
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(DailyWatch20ValidationError, match="positive"):
        load_daily_watch20(root, expected_candidate_pool_mode="ths_hot_strict")


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda rows, receipt: receipt.update(status="failed"), "status is not passed"),
        (lambda rows, receipt: rows.pop(), "must contain 20 rows"),
        (
            lambda rows, receipt: rows.__setitem__(1, {**rows[1], "symbol": rows[0]["symbol"]}),
            "20 unique symbols",
        ),
        (lambda rows, receipt: rows[4].update(sleeve="A"), "A4/B16"),
        (lambda rows, receipt: rows[0].update(tracking_weight=0.2), "must sum to 1.0"),
        (
            lambda rows, receipt: [row.pop("xgb_score") for row in rows],
            "missing required columns",
        ),
        (lambda rows, receipt: rows[0].update(final_score="nan"), "finite numbers"),
        (lambda rows, receipt: rows[-1].update(rank=17), "B ranks must be 1..16"),
        (
            lambda rows, receipt: receipt.update(generated_at="2026-07-10T18:00:00"),
            "must include a timezone",
        ),
        (
            lambda rows, receipt: receipt["minute_features"].pop("lag_trade_days"),
            "minute_features missing fields",
        ),
    ],
)
def test_load_daily_watch20_rejects_invalid_contract(
    tmp_path: Path,
    mutation,
    message: str,
) -> None:
    root = tmp_path / "latest"
    root.mkdir()
    rows = _watchlist_rows()
    receipt = _receipt()
    mutation(rows, receipt)
    calendar_path = root / "trade_cal.parquet"
    pd.DataFrame(
        {
            "cal_date": ["20260709", "20260710", "20260711", "20260712", "20260713"],
            "is_open": [1, 1, 0, 0, 1],
        }
    ).to_parquet(calendar_path)
    receipt["inputs"] = {"trade_cal": str(calendar_path)}
    data_path = root / "watchlist_20.csv"
    pd.DataFrame(rows).to_csv(data_path, index=False)
    receipt["artifacts"] = {
        "watchlist_20.csv": {
            "path": "watchlist_20.csv",
            "sha256": hashlib.sha256(data_path.read_bytes()).hexdigest(),
        }
    }
    (root / "selection_receipt.json").write_text(json.dumps(receipt), encoding="utf-8")

    with pytest.raises(DailyWatch20ValidationError, match=message):
        load_daily_watch20(root)


def test_load_daily_watch20_rejects_stale_source_date(tmp_path: Path) -> None:
    root = _write_artifact(tmp_path / "latest")

    with pytest.raises(DailyWatch20ValidationError, match="stale artifact"):
        load_daily_watch20(root, expected_source_date="20260709")


def test_load_daily_watch20_rejects_tampered_published_file(tmp_path: Path) -> None:
    root = _write_artifact(tmp_path / "latest")
    (root / "watchlist_20.csv").write_text("tampered", encoding="utf-8")

    with pytest.raises(DailyWatch20ValidationError, match="artifact hash mismatch"):
        load_daily_watch20(root)


def test_load_daily_watch20_rejects_stale_minute_cache(tmp_path: Path) -> None:
    root = _write_artifact(tmp_path / "latest")
    receipt_path = root / "selection_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["minute_features"]["as_of"] = "20260709"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    with pytest.raises(DailyWatch20ValidationError, match="stale for required_date"):
        load_daily_watch20(root)


def test_load_daily_watch20_rejects_self_consistent_but_wrong_minute_date(
    tmp_path: Path,
) -> None:
    root = _write_artifact(tmp_path / "latest")
    receipt_path = root / "selection_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["minute_features"]["as_of"] = "20000101"
    receipt["minute_features"]["required_date"] = "20000101"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    with pytest.raises(DailyWatch20ValidationError, match="required_date must be 20260710"):
        load_daily_watch20(root)


def test_load_daily_watch20_rejects_legacy_lag_one_by_default(tmp_path: Path) -> None:
    root = _write_artifact(tmp_path / "latest")
    receipt_path = root / "selection_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["minute_features"] = {
        "enabled": True,
        "as_of": "20260709",
        "required_date": "20260709",
        "lag_trade_days": 1,
    }
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    with pytest.raises(DailyWatch20ValidationError, match="lag_trade_days must be 0"):
        load_daily_watch20(root)
    artifact = load_daily_watch20(root, expected_minute_lag_trade_days=1)
    assert artifact.source_date == "20260710"


def test_companion_json_must_match_csv(tmp_path: Path) -> None:
    root = _write_artifact(tmp_path / "latest")
    rows = _watchlist_rows()
    rows[0]["tracking_weight"] = 0.09
    (root / "watchlist_20.json").write_text(
        json.dumps({"rows": rows}, ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(DailyWatch20ValidationError, match="disagree"):
        load_daily_watch20(root)


def test_daily_watch20_client_and_internal_renderers_are_audience_safe(tmp_path: Path) -> None:
    artifact = load_daily_watch20(_write_artifact(tmp_path / "latest"))

    client_html = build_daily_watch20_html(artifact, audience="client")
    internal_html = build_daily_watch20_html(artifact, audience="internal")
    client_markdown = render_daily_watch20_markdown(artifact, audience="client")
    internal_markdown = render_daily_watch20_markdown(artifact, audience="internal")
    client = render_daily_watch20(artifact, tmp_path / "client", audience="client")
    internal = render_daily_watch20(artifact, tmp_path / "internal", audience="internal")

    assert "今日20只重点关注" in client_html
    assert "关注理由" in client_html
    assert "主要风险" in client_html
    assert "不构成投资建议" in client_html
    assert "数据完整性提示" not in client_html
    assert "序号不代表推荐优先级" in client_html
    assert CLIENT_METHOD_SUMMARY in client_html
    assert "A4" not in client_html
    assert "B16" not in client_html
    assert "DailyWatch20-XGB-v1" not in client_html
    assert "daily_watch20_v1" not in client_html
    assert "综合分" not in client_html
    assert "#f7f4ec" in client_html
    assert "#0d1117" not in client_html
    assert "关注：" in client_markdown
    assert "风险：" in client_markdown
    assert "序号不代表推荐优先级" in client_markdown
    assert CLIENT_METHOD_SUMMARY in client_markdown
    assert "不构成投资建议" in client_markdown
    assert "数据完整性提示" not in client_markdown
    assert "A4" not in client_markdown
    assert "B16" not in client_markdown
    assert "DailyWatch20-XGB-v1" not in client_markdown

    assert "A4 · 模型探索" in internal_html
    assert "B16 · 约束观察" in internal_html
    assert "DailyWatch20-XGB-v1" in internal_html
    assert "daily_watch20_v1" in internal_html
    assert "#f7f4ec" in internal_html
    assert "#0d1117" not in internal_html
    assert "A4 / B16" in internal_markdown
    assert "model=DailyWatch20-XGB-v1" in internal_markdown

    client_png = client.png_path.read_bytes()
    assert client_png.startswith(b"\x89PNG")
    assert struct.unpack(">II", client_png[16:24]) == (1280, 1600)
    assert client.png_path.stat().st_size > 20_000
    assert internal.png_path.read_bytes().startswith(b"\x89PNG")
    assert float(mpimg.imread(internal.png_path)[..., :3].mean()) > 0.65
    assert internal.html_path.is_file()


def test_daily_watch20_client_png_rejects_unsupported_feature_claim(tmp_path: Path) -> None:
    artifact = load_daily_watch20(_write_artifact(tmp_path / "latest"))
    artifact.frame.loc[0, "top_drivers"] = "盈利质量"

    with pytest.raises(DailyWatch20ValidationError, match="unsupported DailyWatch20 feature"):
        generate_daily_watch20_client_png(artifact, tmp_path / "client.png")

    assert not (tmp_path / "client.png").exists()


@pytest.mark.parametrize(
    ("drivers", "risk"),
    [
        ("成交活跃度、尾盘30分钟强弱", "尾盘30分钟强弱偏弱"),
        ("盈利估值、低波动", "20日相对强度偏弱"),
        ("超长且没有任何分隔符的关注理由文本用于检查强制折行", "超长风险说明用于检查省略"),
    ],
)
def test_client_png_reason_and_risk_fit_their_table_cell(drivers: str, risk: str) -> None:
    text = _png_reason_risk_text(drivers, risk)
    lines = text.splitlines()
    width = _client_table_display_budget(3)

    assert 2 <= len(lines) <= 4
    assert lines[0].startswith("关注 ")
    assert any(line.startswith("风险 ") for line in lines)
    assert all(_display_width(line) <= width for line in lines)


def test_light_stock_row_copy_keeps_status_rationale_and_risk_visible() -> None:
    classification, detail, status = _light_stock_row_copy(
        {
            "industry": "半导体设备",
            "theme": "先进制造",
            "top_drivers": "同花顺热榜入池、60日趋势、市场趋势状态",
            "primary_risk": "20日波动偏弱",
            "is_new": True,
        }
    )

    assert classification == "半导体设备 · 先进制造"
    assert detail.startswith("关注 ")
    assert "｜ 风险 " in detail
    assert _display_width(detail) <= 66
    assert status == "新增"


def test_light_overview_keeps_client_status_counts_explicit(tmp_path: Path) -> None:
    artifact = load_daily_watch20(_write_artifact(tmp_path / "latest"))

    overview = dict(_light_overview(artifact))

    assert overview == {"跟踪总数": "20 只", "新增": "2 只", "保留": "18 只"}


def test_daily_watch20_rejects_unknown_renderer_audience(tmp_path: Path) -> None:
    artifact = load_daily_watch20(_write_artifact(tmp_path / "latest"))

    with pytest.raises(ValueError, match="audience"):
        build_daily_watch20_html(artifact, audience="public")
    with pytest.raises(ValueError, match="audience"):
        render_daily_watch20_markdown(artifact, audience="public")


def test_daily_watch20_cli_internal_dry_run_validates_without_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _write_v2_artifact(tmp_path / "latest")
    output = tmp_path / "should-not-exist"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "a-share-daily",
            "daily-watch20",
            "--root",
            str(root),
            "--source-date",
            "20260710",
            "--out-dir",
            str(output),
            "--audience",
            "internal",
            "--dry-run",
        ],
    )

    cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "passed"
    assert payload["counts"] == {"total": 20, "a": 4, "b": 16, "unique": 20}
    assert not output.exists()


def test_daily_watch20_cli_internal_audience_can_open_research_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _write_artifact(tmp_path / "latest")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "a-share-daily",
            "daily-watch20",
            "--root",
            str(root),
            "--audience",
            "internal",
            "--dry-run",
        ],
    )

    cli.main()

    assert json.loads(capsys.readouterr().out)["status"] == "passed"
