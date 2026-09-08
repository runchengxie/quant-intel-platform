from __future__ import annotations

from a_share_daily.freshness import build_freshness_report, render_freshness_section


def test_freshness_report_marks_expected_delay_and_stale_after_retries() -> None:
    freshness = build_freshness_report(
        latest_by_dataset={
            "daily": "20260702",
            "ths_hot": "20260701",
            "margin": "20260630",
        },
        target_date="20260702",
        premium_enabled=True,
        attempts=("github_snapshot", "windows_task_refresh", "report_pipeline_refresh"),
    )

    by_dataset = {item["dataset"]: item for item in freshness["contracts"]}

    assert by_dataset["daily"]["status"] == "fresh"
    assert by_dataset["ths_hot"]["status"] == "stale"
    assert by_dataset["margin"]["status"] == "expected_delay"
    assert not freshness["ok"]

    lines = render_freshness_section(
        {"date": "20260702", "freshness": freshness},
        {"markets": {"cn": {"date": "20260702"}, "us": {"date": "20260701"}}},
    )
    text = "\n".join(lines)

    assert "目标交易日 2026-07-02" in text
    assert "同花顺热榜(ths_hot) 最新 20260701，目标 20260702" in text
    assert "GitHub Actions 快照 + Windows Task Scheduler 补抓 + 报告流水线最终补抓" in text
    assert "融资融券余额(margin) 最新 20260630" in text
    assert "美股新闻/盘前口径: 20260701（上一可用美股交易日）" in text


def test_freshness_report_renders_premium_skips() -> None:
    freshness = build_freshness_report(
        latest_by_dataset={"daily": "20260702"},
        target_date="20260702",
        premium_enabled=False,
        skipped_datasets=("ths_hot",),
    )

    by_dataset = {item["dataset"]: item for item in freshness["contracts"]}
    lines = render_freshness_section({"date": "20260702", "freshness": freshness})
    text = "\n".join(lines)

    assert by_dataset["ths_hot"]["status"] == "skipped"
    assert "skipped 1 项" in text
    assert "已跳过 同花顺热榜(ths_hot)：高权限数据未启用" in text


def test_freshness_report_treats_optional_enhancement_as_degraded() -> None:
    freshness = build_freshness_report(
        latest_by_dataset={"daily": "20260702", "moneyflow_ths": "20260701"},
        target_date="20260702",
        premium_enabled=True,
        refresh_status_by_dataset={
            "moneyflow_ths": {
                "reason": "empty_result",
                "status": "missing",
                "fallback_used": False,
            }
        },
    )

    by_dataset = {item["dataset"]: item for item in freshness["contracts"]}
    lines = render_freshness_section({"date": "20260702", "freshness": freshness})
    text = "\n".join(lines)

    assert freshness["ok"]
    assert by_dataset["moneyflow_ths"]["status"] == "optional_stale"
    assert "optional_degraded 1 项" in text
    assert "接口正常返回但目标日期为空" in text
    assert "不阻断发送" in text


def test_freshness_report_can_skip_dataset_by_config() -> None:
    freshness = build_freshness_report(
        latest_by_dataset={"daily": "20260702", "kpl_list": "20260701"},
        target_date="20260702",
        premium_enabled=True,
        skipped_datasets=("kpl_list",),
        skip_reason_by_dataset={"kpl_list": "disabled_by_config"},
    )

    by_dataset = {item["dataset"]: item for item in freshness["contracts"]}
    lines = render_freshness_section({"date": "20260702", "freshness": freshness})
    text = "\n".join(lines)

    assert freshness["ok"]
    assert by_dataset["kpl_list"]["status"] == "skipped"
    assert by_dataset["kpl_list"]["detail"] == "已按配置暂时关闭"
    assert "optional_degraded 0 项" in text
    assert "已跳过 开盘啦涨停池(kpl_list)：已按配置暂时关闭" in text
