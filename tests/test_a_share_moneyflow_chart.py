from __future__ import annotations

from pathlib import Path

import matplotlib.figure
import pandas as pd

from a_share_daily.charts import moneyflow


def test_moneyflow_chart_converts_source_wanyuan_to_yiyuan(
    tmp_path: Path,
    monkeypatch,
) -> None:
    frame = pd.DataFrame(
        [
            {"name": "流入样本", "ts_code": "000001.SZ", "net_amount": 20_000.0},
            {"name": "流出样本", "ts_code": "000002.SZ", "net_amount": -30_000.0},
        ]
    )
    figures: list[matplotlib.figure.Figure] = []
    monkeypatch.setattr(moneyflow.plt, "close", figures.append)

    output = tmp_path / "moneyflow.png"
    moneyflow.generate_moneyflow(frame, "20260715", str(output))

    assert output.is_file()
    assert len(figures) == 1
    inflow, outflow = figures[0].axes
    assert inflow.get_xlabel() == "净流入（亿元）"
    assert outflow.get_xlabel() == "净流出（亿元）"
    assert "2.0亿" in {item.get_text() for item in inflow.texts}
    assert "3.0亿" in {item.get_text() for item in outflow.texts}
