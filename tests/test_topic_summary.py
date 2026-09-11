from __future__ import annotations

import json
from pathlib import Path

import pytest

from a_share_daily import pipeline
from a_share_daily.charts.topic import generate_topic
from a_share_daily.topic_summary import TopicSummaryError, load_topic_summary


def _write(path: Path, **overrides: object) -> None:
    payload = {
        "schema_version": "daily_watch20.topic_summary.v1",
        "artifact_type": "daily_watch20_topic_summary",
        "source_date": "20260828",
        "signal_date": "20260831",
        "source": "daily_watch20.watchlist_20",
        "aggregation": "selected_watchlist_theme_count_and_weight",
        "topics": [{"topic": "通信与计算", "count": 2, "weight": 1.0, "rank": 1}],
        "quality": {"status": "passed", "selected_count": 2, "topic_count": 1},
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_load_topic_summary_validates_contract_and_dates(tmp_path: Path) -> None:
    path = tmp_path / "topic_summary.json"
    _write(path)

    payload = load_topic_summary(
        path,
        expected_source_date="20260828",
        expected_signal_date="20260831",
    )

    assert payload["topics"][0]["topic"] == "通信与计算"


@pytest.mark.parametrize(
    "overrides",
    [
        {"source_date": "20260827"},
        {"schema_version": "legacy"},
        {"topics": []},
        {"topics": [{"topic": "主题", "count": 1, "weight": -1, "rank": 1}]},
    ],
)
def test_load_topic_summary_rejects_invalid_payload(tmp_path: Path, overrides: dict[str, object]) -> None:
    path = tmp_path / "topic_summary.json"
    _write(path, **overrides)

    with pytest.raises(TopicSummaryError):
        load_topic_summary(path, expected_source_date="20260828", expected_signal_date="20260831")


def test_load_topic_summary_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(TopicSummaryError, match="missing"):
        load_topic_summary(tmp_path / "missing.json")


def test_pipeline_accepts_next_session_signal_for_previous_trade_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "topic_summary.json"
    _write(
        source,
        source_date="20260831",
        signal_date="20260901",
        source="hotspot_composite_v1",
        topics=[{"topic": "人工智能", "count": 1, "weight": 1.0, "rank": 1}],
        quality={"status": "passed", "selected_count": 1, "topic_count": 1},
    )
    monkeypatch.setenv("A_SHARE_TOPIC_SUMMARY_INPUT", str(source))

    result = pipeline.step_topic_summary("20260831")

    assert result["ok"] is True
    assert result["source_date"] == "20260831"
    assert result["signal_date"] == "20260901"


def test_generate_topic_reads_daily_watch20_summary(tmp_path: Path) -> None:
    source = tmp_path / "topic_summary.json"
    _write(source)
    output = tmp_path / "topic.png"

    assert generate_topic(str(source), str(output)) == str(output)
    assert output.is_file()


def test_generate_topic_uses_percentages_dynamic_top_n_and_concentration(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "topic_summary.json"
    _write(
        source,
        topics=[
            {"topic": "金融地产", "count": 5, "weight": 0.65, "rank": 1},
            {"topic": "其他", "count": 2, "weight": 0.15, "rank": 2},
            {"topic": "半导体电子", "count": 1, "weight": 0.10, "rank": 3},
            {"topic": "通信计算", "count": 1, "weight": 0.05, "rank": 4},
            {"topic": "高端制造", "count": 1, "weight": 0.05, "rank": 5},
        ],
        quality={"status": "passed", "selected_count": 10, "topic_count": 5},
    )
    rendered_text: list[str] = []
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure

    original_text = Axes.text
    original_figure_text = Figure.text
    original_set_title = Axes.set_title

    def capture_text(self, x, y, text, *args, **kwargs):
        rendered_text.append(str(text))
        return original_text(self, x, y, text, *args, **kwargs)

    def capture_figure_text(self, x, y, s, *args, **kwargs):
        rendered_text.append(str(s))
        return original_figure_text(self, x, y, s, *args, **kwargs)

    def capture_set_title(self, label, *args, **kwargs):
        rendered_text.append(str(label))
        return original_set_title(self, label, *args, **kwargs)

    monkeypatch.setattr(Axes, "text", capture_text)
    monkeypatch.setattr(Figure, "text", capture_figure_text)
    monkeypatch.setattr(Axes, "set_title", capture_set_title)
    assert generate_topic(str(source), str(tmp_path / "topic.png"))

    assert "65%" in rendered_text
    assert any("Top 5" in text for text in rendered_text)
    assert any("前三主题 90%" in text for text in rendered_text)


def test_generate_topic_rejects_legacy_candidate_universe(tmp_path: Path) -> None:
    source = tmp_path / "candidate_universe.json"
    source.write_text(json.dumps({"topics": [{"topic": "旧主题", "weight": 1.0}]}), encoding="utf-8")

    assert generate_topic(str(source), str(tmp_path / "topic.png")) is None
