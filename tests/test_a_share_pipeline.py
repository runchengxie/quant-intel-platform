from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pandas as pd
import pytest

from a_share_daily import data, pipeline
from a_share_daily.charts.topic import format_topic_label
from a_share_daily.freshness import build_freshness_report


def test_topic_chart_formats_common_english_hotspot_labels() -> None:
    assert format_topic_label("Hotspot") == "热点"
    assert format_topic_label("AI Infrastructure") == "人工智能 基础设施"
    assert format_topic_label("Hot Sectors / Semiconductors") == "热点板块/半导体"


def test_partitioned_reader_reports_missing_dataset_as_file_not_found(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(data, "_data_root", lambda: tmp_path)

    with pytest.raises(FileNotFoundError, match="moneyflow_ths"):
        data._read_partitioned("moneyflow_ths", "20260907")


def test_step_data_freshness_uses_explicit_frozen_snapshot(tmp_path: Path, monkeypatch) -> None:
    snapshot = build_freshness_report(
        latest_by_dataset={"daily": "20260907"},
        target_date="20260907",
        premium_enabled=True,
    )
    snapshot.update(
        {
            "schema_version": "a_share.freshness.snapshot.v1",
            "snapshot_id": "mdp-20260907-test",
        }
    )
    path = tmp_path / "freshness.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    monkeypatch.setenv("A_SHARE_FRESHNESS_SNAPSHOT", str(path))
    monkeypatch.setattr(
        pipeline.D,
        "_latest_date",
        lambda _dataset: (_ for _ in ()).throw(AssertionError("live freshness lookup used")),
    )

    result = pipeline.step_data_freshness("20260907")

    assert result["snapshot_id"] == "mdp-20260907-test"
    assert result["snapshot_source"] == "frozen_snapshot"


def test_step_charts_reports_all_failures_when_daily_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pipeline, "OUTPUT_DIR", tmp_path)

    def fail_read_daily(_trade_date: str) -> pd.DataFrame:
        raise FileNotFoundError("daily partition missing")

    monkeypatch.setattr(pipeline.D, "read_daily", fail_read_daily)

    result = pipeline.step_charts("20260630")

    assert result["ok"] == []
    assert result["degraded"] == []
    assert result["failed"] == list(pipeline.EXPECTED_CHART_KEYS)
    assert result["paths"] == dict.fromkeys(pipeline.EXPECTED_CHART_KEYS)
    assert "daily partition missing" in result["errors"]["daily"]


def test_step_charts_uses_placeholders_for_missing_topic_and_moneyflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(pipeline.PREMIUM_ENV, "1")
    monkeypatch.delenv(pipeline.MONEYFLOW_LATEST_ENV, raising=False)
    monkeypatch.setattr(pipeline, "OUTPUT_DIR", tmp_path)
    daily = pd.DataFrame(
        {
            "ts_code": ["000001.SZ", "000002.SZ", "300001.SZ"],
            "pct_chg": [1.2, -0.5, 2.1],
            "open": [10.0, 20.0, 30.0],
            "high": [10.5, 20.5, 31.0],
            "low": [9.8, 19.8, 29.5],
            "close": [10.3, 19.9, 30.8],
            "pre_close": [10.0, 20.0, 30.0],
            "amount": [1000.0, 2000.0, 3000.0],
            "vol": [100.0, 200.0, 300.0],
        }
    )

    def fake_placeholder(
        *,
        title: str,
        trade_date: str,
        reason: str,
        out_path: str,
    ) -> str:
        path = Path(out_path)
        path.write_text(f"{title}\n{trade_date}\n{reason}", encoding="utf-8")
        return str(path)

    def write_chart(_daily: pd.DataFrame, *_args: object) -> str:
        path = Path(cast(str, _args[-1]))
        path.write_bytes(b"png")
        return str(path)

    monkeypatch.setattr(pipeline.D, "read_daily", lambda _date: daily)
    monkeypatch.setattr(
        pipeline.D,
        "read_limit_list",
        lambda _date: (_ for _ in ()).throw(FileNotFoundError("limit list missing")),
    )
    monkeypatch.setattr(
        pipeline.D,
        "read_moneyflow_ths",
        lambda _date: (_ for _ in ()).throw(FileNotFoundError("moneyflow missing")),
    )
    monkeypatch.setattr(
        pipeline.D,
        "read_margin",
        lambda _date: (_ for _ in ()).throw(FileNotFoundError("margin missing")),
    )
    monkeypatch.setattr(pipeline, "save_unavailable_chart", fake_placeholder)
    monkeypatch.setattr(pipeline, "generate_sentiment", write_chart)
    monkeypatch.setattr(pipeline, "generate_weekly_chart", write_chart)
    monkeypatch.setattr(pipeline, "generate_weekly_text", lambda *_args, **_kwargs: "weekly")

    result = pipeline.step_charts("20260630", universe_json="")

    assert {"topic", "moneyflow"}.issubset(set(result["degraded"]))
    assert "topic" not in result["failed"]
    assert "moneyflow" not in result["failed"]
    assert Path(result["paths"]["topic"]).exists()
    assert Path(result["paths"]["moneyflow"]).exists()
    assert "hotsector 未产出" in result["errors"]["topic"]
    assert result["errors"]["moneyflow"] == "数据文件缺失: moneyflow_ths 20260630"


def test_step_charts_records_empty_hotsector_topic_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(pipeline.PREMIUM_ENV, "1")
    monkeypatch.delenv(pipeline.MONEYFLOW_LATEST_ENV, raising=False)
    monkeypatch.setattr(pipeline, "OUTPUT_DIR", tmp_path)
    universe_json = tmp_path / "candidate_universe.json"
    universe_json.write_text(
        """
        {
          "topics": [],
          "candidate_universe": [],
          "data_sources": {"ths_hot_available": false, "dc_concept_available": false}
        }
        """,
        encoding="utf-8",
    )
    daily = pd.DataFrame(
        {
            "ts_code": ["000001.SZ"],
            "pct_chg": [1.0],
            "open": [10.0],
            "high": [10.5],
            "low": [9.8],
            "close": [10.3],
            "pre_close": [10.0],
            "amount": [1000.0],
            "vol": [100.0],
        }
    )

    def fake_placeholder(
        *,
        title: str,
        trade_date: str,
        reason: str,
        out_path: str,
    ) -> str:
        path = Path(out_path)
        path.write_text(reason, encoding="utf-8")
        return str(path)

    monkeypatch.setattr(pipeline.D, "read_daily", lambda _date: daily)
    monkeypatch.setattr(pipeline.D, "read_limit_list", lambda _date: pd.DataFrame())
    monkeypatch.setattr(
        pipeline.D,
        "read_moneyflow_ths",
        lambda _date: (_ for _ in ()).throw(FileNotFoundError("moneyflow missing")),
    )
    monkeypatch.setattr(
        pipeline.D,
        "read_margin",
        lambda _date: (_ for _ in ()).throw(FileNotFoundError("margin missing")),
    )
    monkeypatch.setattr(pipeline, "save_unavailable_chart", fake_placeholder)
    monkeypatch.setattr(pipeline, "generate_sentiment", lambda *_args: str(tmp_path / "s.png"))
    monkeypatch.setattr(pipeline, "generate_weekly_text", lambda *_args, **_kwargs: "weekly")

    result = pipeline.step_charts("20260630", str(universe_json))

    assert "topic" in result["degraded"]
    assert (
        result["errors"]["topic"]
        == "hotsector 产出 0 只候选，概念数据暂缺。无法生成本交易日主题排名。"
    )


def test_step_hotsector_records_empty_candidate_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(pipeline.PREMIUM_ENV, "1")
    hotsector_dir = tmp_path / "hotsector"
    output_dir = hotsector_dir / "outputs" / "20260630"
    output_dir.mkdir(parents=True)
    input_path = output_dir / "candidate_universe.json"
    input_path.write_text(
        """
        {
          "candidate_universe": [],
          "quality_report": {"reason": "empty_candidate_universe"},
          "data_sources": {"ths_hot_available": false, "dc_concept_available": false}
        }
        """,
        encoding="utf-8",
    )
    monkeypatch.setenv("A_SHARE_HOTSECTOR_INPUT", str(input_path))

    result = pipeline.step_hotsector("20260630")

    assert result["ok"] is False
    assert result["candidates"] == 0
    assert result["reason"] == "hotsector 产出 0 只候选，概念数据暂缺"
    assert result["data_sources"]["ths_hot_available"] is False


def test_step_charts_skips_premium_charts_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(pipeline.PREMIUM_ENV, raising=False)
    monkeypatch.setattr(pipeline, "OUTPUT_DIR", tmp_path)
    daily = pd.DataFrame(
        {
            "ts_code": ["000001.SZ"],
            "pct_chg": [1.0],
            "open": [10.0],
            "high": [10.5],
            "low": [9.8],
            "close": [10.3],
            "pre_close": [10.0],
            "amount": [1000.0],
            "vol": [100.0],
        }
    )

    monkeypatch.setattr(pipeline.D, "read_daily", lambda _date: daily)
    monkeypatch.setattr(pipeline.D, "read_limit_list", lambda _date: pd.DataFrame())
    monkeypatch.setattr(
        pipeline.D,
        "read_margin",
        lambda _date: (_ for _ in ()).throw(FileNotFoundError("margin missing")),
    )
    monkeypatch.setattr(pipeline, "generate_sentiment", lambda *_args: str(tmp_path / "s.png"))
    monkeypatch.setattr(pipeline, "generate_weekly_text", lambda *_args, **_kwargs: "weekly")

    result = pipeline.step_charts("20260630", universe_json="")

    assert {"topic", "moneyflow"} == set(result["skipped"])
    assert "topic" not in result["degraded"]
    assert "moneyflow" not in result["degraded"]
    assert "topic" not in result["failed"]
    assert "moneyflow" not in result["failed"]


def test_step_hotsector_skips_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(pipeline.PREMIUM_ENV, raising=False)

    result = pipeline.step_hotsector("20260630")

    assert result["skipped"] is True
    assert result["reason"] == "高权限 TuShare 主题数据未启用"


def test_step_hotsector_does_not_execute_retired_owner_without_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(pipeline.PREMIUM_ENV, "1")
    monkeypatch.delenv("A_SHARE_HOTSECTOR_INPUT", raising=False)

    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("retired hotsector owner must not be executed")

    monkeypatch.setattr(pipeline, "_run", fail_if_called)

    result = pipeline.step_hotsector("20260630")

    assert result["skipped"] is True
    assert result["ok"] is False
    assert "research-workspace" in result["reason"]


def test_step_data_freshness_skips_configured_report_datasets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(pipeline.PREMIUM_ENV, "1")
    monkeypatch.setenv(pipeline.DISABLED_REPORT_DATASETS_ENV, "moneyflow_ths,kpl_list")

    def fake_latest_date(dataset: str, *, as_of_date: str | None = None) -> str:
        if dataset in {"moneyflow_ths", "kpl_list"}:
            return "20260628"
        return "20260630"

    monkeypatch.setattr(pipeline.D, "_latest_date", fake_latest_date)
    monkeypatch.setattr(pipeline, "_load_report_refresh_status", lambda _date: {})

    result = pipeline.step_data_freshness("20260630")
    by_dataset = {item["dataset"]: item for item in result["contracts"]}

    assert result["ok"] is True
    assert by_dataset["moneyflow_ths"]["status"] == "skipped"
    assert by_dataset["moneyflow_ths"]["detail"] == "已按配置暂时关闭"
    assert by_dataset["kpl_list"]["status"] == "skipped"
    assert result["optional_issues"] == []
