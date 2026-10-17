"""Draw concise weekly charts from facts already present in the report."""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

from a_share_analysis.weekly_visual_facts import WeeklyFacts

WIDTH = 1200
PAPER = "#f7f4ef"
INK = "#262626"
MUTED = "#777c83"
GRID = "#dedbd5"
BLUE = "#376b83"
GOLD = "#c19b49"


class Panel:
    def __init__(self, title: str, height: int, font_path: str):
        self.image = Image.new("RGB", (WIDTH, height), PAPER)
        self.draw = ImageDraw.Draw(self.image)
        self.font_path = font_path
        self.text(60, 25, title, 38)

    def text(self, x: float, y: float, text: str, size: int = 27, color: str = INK) -> None:
        self.draw.text((x, y), text, fill=color, font=ImageFont.truetype(self.font_path, size))

    def track(self, x: float, y: float, width: float, fraction: float, color: str = BLUE) -> None:
        self.draw.rounded_rectangle((x, y, x + width, y + 18), radius=8, fill=GRID)
        if fraction > 0:
            self.draw.rounded_rectangle(
                (x, y, x + width * min(fraction, 1), y + 18), radius=8, fill=color
            )


def market_panel(facts: WeeklyFacts, font_path: str) -> Image.Image | None:
    m = facts.market
    if not m:
        return None
    p = Panel("本周市场 · 交易与资金", 475, font_path)
    if "days" in m:
        p.text(60, 91, f"{m['days']:.0f} 个交易日", 26, MUTED)
        categories = [("上涨", m["up"], BLUE), ("下跌", m["down"], GOLD)]
        flat = m["days"] - m["up"] - m["down"]
        if flat:
            categories.append(("平盘", flat, MUTED))
        x = 300.0
        for label, count, color in categories:
            width = 820 * count / m["days"]
            if width:
                p.draw.rectangle((x, 91, x + width, 139), fill=color)
                p.text(x + 12, 98, f"{label} {count:.0f} 天", 26, "white")
            x += width
    fields = [
        ("turnover", "全周成交额", "万亿元", ".2f"),
        ("flow", "主力资金净流向", "亿元", "+.0f"),
        ("limit_ups", "全周涨停", "只", ".0f"),
        ("up_share", "日均上涨家数占比", "%", ".0f"),
        ("mean_return", "个股平均涨幅", "%", "+.2f"),
        ("gold_return", "黄金本周涨跌", "%", "+.1f"),
    ]
    for i, (key, label, unit, fmt) in enumerate(fields):
        x, y = 60 + i % 3 * 365, 180 + i // 3 * 130
        p.text(x, y, label, 25, MUTED)
        if key in m:
            p.text(x, y + 38, f"{m[key]:{fmt}} {unit}", 36, BLUE if m[key] >= 0 else INK)
        else:
            p.text(x, y + 38, "未提供", 30, MUTED)
        subkey = {"turnover": "daily_turnover", "limit_ups": "daily_limit_ups"}.get(key)
        if subkey in m:
            p.text(x, y + 82, f"日均 {m[subkey]:g} {unit}", 22, MUTED)
    p.text(60, 446, "成交额、资金流向与涨停数采用原报告口径，单位分别标注。", 22, MUTED)
    return p.image


def history_panel(facts: WeeklyFacts, font_path: str) -> Image.Image | None:
    if not facts.outcomes:
        return None
    p = Panel("相同状态之后 · 历史分布摘要", 210 + 88 * len(facts.outcomes), font_path)
    p.text(60, 85, facts.sample_note, 25, MUTED)
    p.text(270, 130, "后续收益中位数", 26)
    p.text(750, 130, "正收益比例", 26)
    p.text(1030, 130, "样本周数", 24)
    lower = min(0.0, min(row.median for row in facts.outcomes))
    upper = max(1.0, max(row.median for row in facts.outcomes))
    span = upper - lower
    zero = 270 + (0 - lower) / span * 380
    for i, row in enumerate(facts.outcomes):
        y = 181 + i * 88
        p.text(60, y, f"{row.weeks} 周后", 28)
        end = 270 + (row.median - lower) / span * 380
        p.draw.line((zero, y - 7, zero, y + 41), fill=MUTED, width=2)
        p.draw.rectangle((min(zero, end), y + 8, max(zero, end), y + 29), fill=BLUE)
        p.text(666, y, f"{row.median:+.1f}%", 25)
        p.track(750, y + 12, 195, row.win_rate / 100)
        p.text(954, y, f"{row.win_rate:.0f}%", 25)
        p.text(1055, y, str(row.samples), 25, MUTED)
    p.text(
        270,
        177 + len(facts.outcomes) * 88,
        f"收益轴 {lower:g}% 至 {upper:g}% · 零线已标",
        22,
        MUTED,
    )
    return p.image


def methods_panel(facts: WeeklyFacts, font_path: str) -> Image.Image | None:
    if not facts.methods:
        return None
    p = Panel("价值方法对照 · 同口径看差异", 165 + 155 * len(facts.methods), font_path)
    p.text(485, 92, "近 12 周", 26)
    p.text(690, 92, "近 52 周", 26)
    p.text(890, 92, "当前回撤", 26)
    for i, row in enumerate(facts.methods):
        y = 148 + i * 155
        p.text(60, y, row.name, 28)
        p.text(60, y + 43, f"截至 {row.date}", 23, MUTED)
        for x, value in ((485, row.ret12), (690, row.ret52), (890, row.drawdown)):
            p.text(x, y, f"{value:+.1f}%", 33, BLUE if value > 0 else INK)
        p.text(60, y + 88, "12 周收益的历史分位", 24, MUTED)
        p.track(360, y + 99, 610, row.percentile / 100, GOLD)
        p.text(995, y + 84, f"{row.percentile:.0f}%", 30)
    return p.image


def observation_panel(facts: WeeklyFacts, font_path: str) -> Image.Image | None:
    if not facts.observations:
        return None
    items = list(facts.observations)
    extra = 220 if facts.crowding else 0
    p = Panel("下周观察 · 阈值与信号", 110 + extra + 95 * len(items), font_path)
    for i, (key, value) in enumerate(facts.crowding.items()):
        y = 110 + i * 90
        label = "小盘拥挤度 · ≥0.90 触发" if key == "small" else "大盘拥挤度 · ≤0.10 触发"
        threshold = 0.90 if key == "small" else 0.10
        p.text(60, y, label, 25)
        p.track(460, y + 13, 505, value)
        marker = 460 + 505 * threshold
        p.draw.line((marker, y + 4, marker, y + 42), fill=GOLD, width=4)
        p.text(1000, y - 2, f"{value:.3f}", 30)
    shortened = {
        "当前方向不明显。": "价值方向：尚不明确",
        "配置上可保持当前的价值风格比例，避免根据单周波动频繁调整。": "配置比例保持 → 避免单周频繁调整",
        "观察相对强弱短均线是否跌破长均线。": "方向观察：短均线 < 长均线？",
        "观察近 20 日拥挤证据是否回落至 0.90 以下。": "拥挤观察：20 日证据 < 0.90？",
    }
    for i, text in enumerate(items):
        y = 108 + extra + i * 95
        text = shortened.get(text, text)
        p.draw.ellipse((60, y + 4, 100, y + 44), fill=BLUE)
        p.text(72, y + 5, str(i + 1), 25, "white")
        # Wrap labels without shortening or inventing a numeric trajectory.
        font = ImageFont.truetype(font_path, 27)
        lines, current = [], ""
        for char in text:
            if current and font.getlength(current + char) > 980:
                lines.append(current)
                current = ""
            current += char
        lines.append(current)
        if len(lines) > 2:
            raise ValueError("weekly observation exceeds its readable panel")
        for j, line in enumerate(lines):
            p.text(130, y + j * 37, line)
    return p.image


def visual_panels(facts: WeeklyFacts, font_path: str) -> list[Image.Image]:
    return [
        image
        for render in (history_panel, methods_panel, observation_panel)
        if (image := render(facts, font_path)) is not None
    ]
