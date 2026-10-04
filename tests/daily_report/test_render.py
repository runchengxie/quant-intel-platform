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
    text = render_markdown(report, locale="zh-CN")
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
    text = render_markdown(report, locale="zh-CN")
    assert "市场日报（2026-09-23）" in text
    assert "标普收跌 0.8%" in text
    assert "核实截至" in text


def test_render_markdown_supports_english_shell_without_translating_source_facts():
    report = DailyReport(
        schema_version="1.0",
        as_of=datetime(2026, 9, 24, 9, tzinfo=UTC),
        generated_at=datetime(2026, 9, 24, 9, tzinfo=UTC),
        run_id="daily-2026-09-23",
        sections=(ReportSection("market", "市场表现"),),
        quality_summary={"status": "degraded"},
        missing_sources=("quotes",),
    )

    text = render_markdown(report, locale="en-US")

    assert "# Market report (2026-09-23)" in text
    assert "## Market performance" in text
    assert "Data status: degraded" in text
    assert "## Data gaps" in text
    assert "暂无已校验内容。" not in text


def test_render_revision_labels_date_only_evidence_in_both_locales():
    report = DailyReport(
        schema_version="1.1",
        as_of=datetime(2026, 10, 2, 23, tzinfo=UTC),
        generated_at=datetime(2026, 10, 4, 1, tzinfo=UTC),
        run_id="daily-2026-10-02",
        sections=(ReportSection("company_news", "公司新闻", claims=("news",)),),
        events=(
            MarketEvent(
                "news",
                "web_company_news_event",
                "Release",
                "Revenue grew",
                None,
                None,
                None,
                "issuer",
                "https://issuer.test",
                None,
                "reviewed",
                "date",
                "2026-10-02",
                "unknown",
                "publication",
                "background",
            ),
        ),
        claims=(ResearchClaim("Revenue grew", ("news",), ("https://issuer.test",), "confirmed"),),
        quality_summary={
            "revision": "news_only",
            "news_revision": {
                "revised_at": "2026-10-04T01:00:00+00:00",
                "news_cutoff": "2026-10-04T00:00:00+00:00",
            },
        },
    )
    for locale, labels in [
        ("en-US", ["Market facts cutoff", "News revised", "Date only", "Timezone unknown"]),
        ("zh-CN", ["行情截至", "新闻修订", "仅提供日期", "时区未知"]),
    ]:
        text = render_markdown(report, locale=locale)
        assert all(label in text for label in labels)
        assert "2026-10-02" in text
        assert "2026-10-02T00:00" not in text
