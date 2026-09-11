import json
from pathlib import Path

from matplotlib.axes import Axes

from a_share_daily.charts.market_temperature import generate_market_temperature, run


def test_generate_market_temperature_writes_chart(tmp_path: Path) -> None:
    out_path = tmp_path / "nested" / "market_temperature.png"
    temperature = {
        "status": "热而脆",
        "heat": 78,
        "fragility": 66.5,
        "dimensions": {
            "流动性": 82,
            "广度": 61,
            "赚钱效应": 73,
            "亏钱风险": 68,
            "趋势确认": 55,
            "轮动质量": 47,
        },
        "contradictions": [
            "指数上涨但个股中位数偏弱",
            "成交放大但高位股亏钱效应同步上升",
        ],
    }

    result = generate_market_temperature(temperature, "20260715", str(out_path))

    assert result == str(out_path)
    assert out_path.is_file()
    assert out_path.stat().st_size > 10_000


def test_generate_market_temperature_marks_missing_and_limits_conflicts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    rendered_text: list[str] = []
    original_text = Axes.text

    def capture_text(self, x, y, text, *args, **kwargs):
        rendered_text.append(str(text))
        return original_text(self, x, y, text, *args, **kwargs)

    monkeypatch.setattr(Axes, "text", capture_text)
    out_path = tmp_path / "partial.png"
    temperature = {
        "state": "数据分化",
        "heat_score": 52,
        "six_dimensions": {"volume": 64},
        "core_contradictions": ["矛盾一", "矛盾二", "不应展示的矛盾三"],
    }

    generate_market_temperature(temperature, "2026-07-15", str(out_path))

    assert out_path.is_file()
    assert "数据分化" in rendered_text
    assert sum(text == "N/A" for text in rendered_text) >= 6
    assert any("矛盾一" in text for text in rendered_text)
    assert any("矛盾二" in text for text in rendered_text)
    assert not any("矛盾三" in text for text in rendered_text)
    assert "观察分 / 未回测 / 不直接映射仓位" in rendered_text


def test_market_temperature_cli_reads_evening_review(tmp_path: Path) -> None:
    review_json = tmp_path / "evening_review.json"
    out_path = tmp_path / "temperature.png"
    review_json.write_text(
        json.dumps(
            {
                "trade_date": "20260715",
                "market_temperature": {
                    "status_label": "结构分化且脆弱",
                    "heat_score": 44.4,
                    "fragility_score": 59.2,
                    "dimensions": {},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    exit_code = run(["--review-json", str(review_json), "--out", str(out_path)])

    assert exit_code == 0
    assert out_path.is_file()


def test_market_temperature_uses_dot_scale_and_semantic_risk_note(
    tmp_path: Path, monkeypatch
) -> None:
    rendered_text: list[str] = []
    original_text = Axes.text

    def capture_text(self, x, y, text, *args, **kwargs):
        rendered_text.append(str(text))
        return original_text(self, x, y, text, *args, **kwargs)

    monkeypatch.setattr(Axes, "text", capture_text)
    generate_market_temperature(
        {
            "status": "数据分化",
            "heat_score": 32,
            "fragility_score": 62,
            "dimensions": {"广度": 24.4, "亏钱风险": 59.5},
        },
        "20260715",
        str(tmp_path / "temperature.png"),
    )

    assert "0" in rendered_text and "50" in rendered_text and "100" in rendered_text
    assert "风险偏高" in rendered_text
    assert not any(text == "统一按 0–100 展示" for text in rendered_text)
