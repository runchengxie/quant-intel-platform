from datetime import UTC, datetime

from daily_messenger.daily_report.models import DailyReport
from daily_messenger.daily_report.render import render_markdown


def test_render_markdown_includes_sections_and_degraded_status():
    report = DailyReport(
        schema_version="1.0", as_of=datetime(2026, 9, 19, tzinfo=UTC),
        generated_at=datetime(2026, 9, 19, tzinfo=UTC), run_id="run",
        quality_summary={"status": "degraded"},
    )
    text = render_markdown(report)
    assert "市场表现" in text
    assert "degraded" in text
