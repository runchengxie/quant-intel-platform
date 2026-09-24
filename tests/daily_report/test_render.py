from datetime import UTC, datetime

from daily_messenger.daily_report.models import (
    DailyReport,
    MarketEvent,
    ReportSection,
    ResearchClaim,
)
from daily_messenger.daily_report.render import render_markdown


def test_render_markdown_includes_sections_and_degraded_status():
    report = DailyReport(
        schema_version="1.0",
        as_of=datetime(2026, 9, 19, tzinfo=UTC),
        generated_at=datetime(2026, 9, 19, tzinfo=UTC),
        run_id="run",
        quality_summary={"status": "degraded"},
    )
    text = render_markdown(report)
    assert "市场表现" in text
    assert "degraded" in text


def test_render_shows_reviewed_summary_even_when_section_has_facts():
    source_time = datetime(2026, 9, 23, 20, 12, tzinfo=UTC)
    report = DailyReport(
        schema_version="1.0",
        as_of=datetime(2026, 9, 24, 9, tzinfo=UTC),
        generated_at=datetime(2026, 9, 24, 9, tzinfo=UTC),
        run_id="daily-2026-09-23",
        sections=(
            ReportSection(
                "market", "市场表现", facts=("index.spx.change_percent",), claims=("reviewed.0",)
            ),
        ),
        events=(
            MarketEvent(
                "reviewed.0",
                "web_market_close",
                "AP recap",
                None,
                None,
                None,
                None,
                "AP",
                "https://abcnews.com/article",
                source_time,
                "reviewed",
            ),
        ),
        claims=(
            ResearchClaim(
                "标普收跌 0.8%", ("reviewed.0",), ("https://abcnews.com/article",), "confirmed"
            ),
        ),
    )
    text = render_markdown(report)
    assert "市场日报（2026-09-23）" in text
    assert "标普收跌 0.8%" in text
    assert "核实截至" in text
