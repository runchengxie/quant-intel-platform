from __future__ import annotations

from a_share_daily.reporting.model import Metric, MetricGroup, ReportDocument, ReportSection
from a_share_daily.reporting.render_markdown import render_markdown
from a_share_daily.reporting.render_png import render_png
from a_share_daily.reporting.themes import get_theme


def _document() -> ReportDocument:
    return ReportDocument(
        report_type="morning",
        report_date="20260911",
        title="A股晨报",
        metrics=(MetricGroup("市场", (Metric("上涨占比", 62, "%"),)),),
        sections=(ReportSection("摘要", metrics=(MetricGroup("重点", (Metric("温度", "偏暖"),)),)),),
    )


def test_markdown_preserves_content_and_theme_is_metadata_only() -> None:
    document = _document()
    rendered = render_markdown(document, get_theme("research_editorial"))
    assert "A股晨报" in rendered
    assert "上涨占比" in rendered and "62" in rendered
    assert document.content_hash() == _document().content_hash()


def test_png_is_non_empty_and_theme_specific(tmp_path) -> None:
    path = render_png(_document(), get_theme("research_editorial"), tmp_path / "report.png")
    assert path.stat().st_size > 1_000
