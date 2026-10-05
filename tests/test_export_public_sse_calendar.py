"""The public calendar exporter publishes only verified SSE date flags."""

import json

import pandas as pd
import pytest

from project_tools.export_public_sse_calendar import export_calendar


def owner_frame():
    return pd.DataFrame(
        {
            "exchange": "SSE",
            "cal_date": pd.date_range("2026-01-01", "2026-12-31").strftime("%Y%m%d"),
            "is_open": 0,
            "private_column": "must not publish",
        }
    )


def test_export_only_safe_sse_projection(tmp_path):
    frame = owner_frame()
    frame.loc[0, "is_open"] = 1
    source = tmp_path / "owner.parquet"
    pd.concat([frame, frame.assign(exchange="SZSE")]).to_parquet(source)
    output = tmp_path / "public.json"
    export_calendar(source, output, 2026, "https://www.sse.com.cn/reference")
    payload = json.loads(output.read_text())
    assert len(payload["days"]) == 365
    assert payload["days"]["2026-01-01"] is True
    assert len(payload["source_sha256"]) == 64
    assert "private_column" not in output.read_text()
    assert "must not publish" not in output.read_text()


@pytest.mark.parametrize("fault", ["gap", "duplicate", "invalid_flag"])
def test_export_rejects_bad_owner_rows(tmp_path, fault):
    frame = owner_frame()
    if fault == "gap":
        frame = frame.iloc[1:]
    elif fault == "duplicate":
        frame = pd.concat([frame, frame.iloc[:1]])
    else:
        frame.loc[0, "is_open"] = 2
    source = tmp_path / "owner.parquet"
    frame.to_parquet(source)
    output = tmp_path / "public.json"
    with pytest.raises(ValueError):
        export_calendar(source, output, 2026, "https://www.sse.com.cn/reference")
    assert not output.exists()
