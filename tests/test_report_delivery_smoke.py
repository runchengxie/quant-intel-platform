"""冒烟测试：report_delivery.py 中纯函数与图表时效判断。

无网络依赖，是后续把 report_delivery 按职责拆分到 `a_share_daily/delivery/`
前的回归安全网。
"""

import os

from a_share_daily.delivery import io_util, report_delivery


def test_fmt_pct():
    assert report_delivery._fmt_pct(1.234) == "+1.23%"
    assert report_delivery._fmt_pct(-2.5) == "-2.50%"
    assert report_delivery._fmt_pct("bad") == "n/a"


def test_fmt_close():
    assert report_delivery._fmt_close(1234.5) == "1,234"
    assert report_delivery._fmt_close(12.345) == "12.35"
    assert report_delivery._fmt_close("bad") == "n/a"


def test_fmt_yuan():
    assert report_delivery._fmt_yuan(1.5e8) == "1.50亿"
    assert report_delivery._fmt_yuan(2e4) == "2.00万"
    assert report_delivery._fmt_yuan(3e12) == "3.00万亿"
    assert report_delivery._fmt_yuan("bad") == "n/a"


def test_date_dash():
    assert report_delivery._date_dash("20260727") == "2026-07-27"
    assert report_delivery._date_dash("2026-07-27") == "2026-07-27"


def test_dict_and_list_coercion():
    assert report_delivery._dict({"a": 1}) == {"a": 1}
    assert report_delivery._dict(None) == {}
    assert report_delivery._list([1, 2]) == [1, 2]
    assert report_delivery._list(None) == []


def test_chart_stale_tolerance_from_env(monkeypatch):
    monkeypatch.setenv("A_SHARE_CHART_STALE_TOLERANCE_SECONDS", "60")
    assert io_util._chart_stale_tolerance_seconds() == 60.0
    monkeypatch.setenv("A_SHARE_CHART_STALE_TOLERANCE_SECONDS", "garbage")
    assert io_util._chart_stale_tolerance_seconds() == 1800.0


def test_resolve_chart_path_finds_existing_relative(tmp_path):
    chart = tmp_path / "chart.png"
    chart.write_text("x")
    resolved = io_util._resolve_chart_path(str(chart), tmp_path)
    assert resolved == chart.resolve()


def test_chart_is_fresh_without_manifest(tmp_path):
    chart = tmp_path / "chart.png"
    chart.write_text("x")
    assert io_util._chart_is_fresh(chart, None) is True


def test_chart_is_fresh_when_older_than_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("A_SHARE_CHART_STALE_TOLERANCE_SECONDS", "0")
    chart = tmp_path / "chart.png"
    chart.write_text("x")
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}")
    # 让 manifest 比 chart 新
    older = chart.stat().st_mtime - 10
    os.utime(chart, (older, older))
    newer = manifest.stat().st_mtime + 10
    os.utime(manifest, (newer, newer))
    assert io_util._chart_is_fresh(chart, manifest) is False
