from __future__ import annotations

from a_share_daily.market_temperature import build_market_temperature
from a_share_daily.market_temperature_render import render_market_temperature_section


def _full_contract_payload() -> dict:
    return {
        "status_label": "结构性修复",
        "heat_score": 72,
        "fragility_score": 58.5,
        "dimensions": [
            {
                "key": "volume",
                "label": "量能",
                "score": 68,
                "status": "温和放量",
                "evidence": "成交额 2.59 万亿",
            },
            {
                "key": "breadth",
                "label": "广度",
                "score": 75,
                "status": "多数上涨",
                "evidence": "上涨率 60.7%",
            },
            {
                "key": "profit_effect",
                "label": "赚钱效应",
                "score": 62,
                "status": "局部活跃",
                "evidence": "涨停 73 家",
            },
            {
                "key": "loss_effect",
                "label": "亏钱效应",
                "score": 71,
                "status": "尾部风险偏高",
                "evidence": "跌幅>5% 478 家 | 跌停约 56 家",
            },
            {
                "key": "funds",
                "label": "资金",
                "score": 34,
                "status": "净流出",
                "evidence": "主力净流出 400 亿元",
            },
            {
                "key": "rotation",
                "label": "轮动",
                "score": 66,
                "status": "医药消费占优",
                "evidence": "医药生物 +3.12%",
            },
        ],
        "core_tensions": [
            {
                "tension": "广度修复但权重承压",
                "evidence": "中位数 +0.77%，加权 -1.67%",
                "implication": "指数不能代表多数个股体感",
            }
        ],
        "validation_conditions": [
            {
                "condition": "成交与广度共同维持",
                "confirm_if": "成交额不低于 2.4 万亿且上涨率高于 55%",
                "invalidate_if": "上涨率跌破 40%",
            }
        ],
        "previous_validation": [
            {
                "claim": "风险偏好修复",
                "result": "部分验证",
                "evidence": "上涨率改善，但权重与资金走弱",
            }
        ],
        "confidence": {
            "level": "中",
            "available_dimensions": 6,
            "total_dimensions": 6,
            "warnings": ["跌停家数为近似值", "两融数据 T+1"],
        },
        "calibration": {
            "status": "观察期",
            "version": "v1",
            "sample_size": 12,
            "note": "尚未完成收益或仓位映射校准",
        },
    }


def test_render_market_temperature_section_renders_full_contract() -> None:
    payload = _full_contract_payload()

    lines = render_market_temperature_section(payload)
    text = "\n".join(lines)

    assert lines[:4] == [
        "## 一、市场状态",
        "- 状态: 结构性修复。",
        "- 热度 / 脆弱度: 72 / 58.5（观察分）。",
        "- 口径: 热度、脆弱度与六维分数均为市场状态观察分，不直接映射仓位，也不构成交易指令。",
    ]
    assert "| 亏钱效应 | 71 | 尾部风险偏高 | 跌幅>5% 478 家 \\| 跌停约 56 家 |" in lines
    assert sum(line.startswith("| ") for line in lines[7:]) == 7
    assert "### 核心矛盾" in lines
    assert (
        "- 广度修复但权重承压；证据: 中位数 +0.77%，加权 -1.67%；含义: 指数不能代表多数个股体感"
        in lines
    )
    assert "### 明日验证" in lines
    assert "确认: 成交额不低于 2.4 万亿且上涨率高于 55%" in text
    assert "### 昨日验证复盘" in lines
    assert "结果: 部分验证" in text
    assert "- 完整度: 中；六维可用: 6/6。" in lines
    assert "- 警告: 跌停家数为近似值；两融数据 T+1。" in lines
    assert "- 校准: 观察期；版本 v1；样本 12；尚未完成收益或仓位映射校准。" in lines


def test_render_market_temperature_section_keeps_missing_values_visible() -> None:
    lines = render_market_temperature_section({})
    text = "\n".join(lines)

    assert "- 状态: N/A。" in lines
    assert "- 热度 / 脆弱度: N/A / N/A（观察分）。" in lines
    for label in ("流动性", "广度", "赚钱效应", "亏钱风险", "趋势确认", "轮动质量"):
        assert f"| {label} | N/A | N/A | N/A |" in lines
    assert text.count("### ") == 5
    assert text.count("- N/A") == 3
    assert "- 完整度: N/A；六维可用: N/A。" in lines
    assert "- 警告: N/A。" in lines
    assert "- 校准: N/A。" in lines


def test_render_market_temperature_section_accepts_aliases_and_mapping_dimensions() -> None:
    payload = {
        "state": {"label": "分歧修复", "heat": {"value": 61}},
        "vulnerability_score": "47.25",
        "six_dimensions": {
            "turnover": {"value": 55, "state": "缩量", "facts": ["低于 5 日均量"]},
            "market_breadth": {"score": 63, "signal": "扩散", "detail": "上涨 3200 家"},
        },
        "core_conflicts": "指数与个股体感背离",
        "tomorrow_checks": {"成交额": "高于 5 日均值"},
        "previous_checks": ["昨日判断缺少可比基线"],
        "data_confidence": "低",
        "calibration_status": "未校准",
    }

    lines = render_market_temperature_section(payload, heading="## 市场温度")

    assert lines[0] == "## 市场温度"
    assert "- 状态: 分歧修复。" in lines
    assert "- 热度 / 脆弱度: 61 / 47.25（观察分）。" in lines
    assert "| 流动性 | 55 | 缩量 | 低于 5 日均量 |" in lines
    assert "| 广度 | 63 | 扩散 | 上涨 3200 家 |" in lines
    assert "- 指数与个股体感背离" in lines
    assert "- 成交额: 高于 5 日均值" in lines
    assert "- 昨日判断缺少可比基线" in lines
    assert "- 完整度: 低；六维可用: 2/6。" in lines
    assert "- 警告: 缺少 赚钱效应、亏钱风险、趋势确认、轮动质量。" in lines
    assert "- 校准: 未校准。" in lines


def test_render_market_temperature_section_normalizes_multiline_text() -> None:
    lines = render_market_temperature_section(
        {
            "status_label": "结构性\n行情",
            "core_tensions": ["资金走弱\n但广度改善"],
        }
    )

    assert "- 状态: 结构性 行情。" in lines
    assert "- 资金走弱 但广度改善" in lines


def test_render_previous_validation_translates_machine_status() -> None:
    lines = render_market_temperature_section(
        {
            "previous_validation": [
                {
                    "description": "上涨广度继续修复",
                    "metric": "breadth_up_ratio",
                    "operator": ">",
                    "target": 0.55,
                    "observed": 0.61,
                    "status": "confirmed",
                }
            ]
        }
    )

    assert "- 上涨广度继续修复；结果: 已验证；观测: 61.0%；条件: 上涨率 > 55.0%" in lines


def test_render_market_temperature_section_consumes_calculator_output() -> None:
    payload = build_market_temperature(
        "20260715",
        overview={
            "turnover_total": 2_000_000_000_000,
            "breadth": {"up": 3_200, "down": 1_900, "flat": 100, "total": 5_200},
            "median_pct_chg": 0.55,
            "vwap_above_ratio": 53,
            "up5_count": 240,
            "down5_count": 120,
        },
        indices={
            "index_positive_ratio": 0.6,
            "index_median_return": 0.004,
            "index_close_position": 0.58,
        },
        limits={
            "limit_up_ratio": 0.012,
            "limit_down_ratio": 0.004,
            "seal_rate": 0.72,
        },
        moneyflow={
            "moneyflow": {
                "inflow_stocks": 2_800,
                "outflow_stocks": 2_300,
                "net_in": 120,
                "net_out": -90,
            }
        },
        industries={
            "industry_positive_ratio": 0.65,
            "industry_median_return": 0.006,
            "leadership_concentration": 0.35,
        },
        turnover_history=[
            1_500_000_000_000,
            1_600_000_000_000,
            1_700_000_000_000,
            1_800_000_000_000,
            1_900_000_000_000,
        ],
    )

    lines = render_market_temperature_section(payload)
    dimension_rows = [line for line in lines if line.startswith("| ")][1:]
    text = "\n".join(lines)

    assert len(dimension_rows) == 6
    for label in ("流动性", "广度", "赚钱效应", "亏钱风险", "趋势确认", "轮动质量"):
        assert any(row.startswith(f"| {label} |") for row in dimension_rows)
    assert all("| N/A | N/A | N/A |" not in row for row in dimension_rows)
    assert "六维可用: 6/6" in text
    assert "暂定观察刻度（未回测）" in text
    assert "不直接映射仓位" in text
