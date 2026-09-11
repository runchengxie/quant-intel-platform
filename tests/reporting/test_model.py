from __future__ import annotations

from a_share_daily.reporting.model import (
    Metric,
    MetricGroup,
    Notice,
    PositionCard,
    ReportDocument,
    ReportSection,
    SeriesChart,
)


def _document() -> ReportDocument:
    return ReportDocument(
        report_type="weekly",
        report_date="20260911",
        title="周度组合",
        metrics=(MetricGroup("变动", (Metric("新增", 2),)),),
        sections=(
            ReportSection(
                title="组合",
                positions=(PositionCard("AAA", "甲公司", "新增", "dailywatch_family"),),
                charts=(SeriesChart("净值", (("20260901", 1.0), ("20260911", 1.1))),),
            ),
        ),
        notices=(Notice("研究观察用途", "info"),),
    )


def test_equal_documents_have_equal_content_hash() -> None:
    assert _document().content_hash() == _document().content_hash()


def test_theme_metadata_is_not_part_of_content_hash() -> None:
    document = _document()
    assert document.with_metadata(theme="dark_terminal").content_hash() == document.content_hash()
