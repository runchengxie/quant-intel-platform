"""Compose validated weekly decision cards into one mobile-readable report image."""

from __future__ import annotations

import argparse
import re
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from a_share_daily.data import cjk_font_path

WIDTH = 1200
MAX_HEIGHT = 12000
MAX_BYTES = 10_000_000
PAPER = "#f7f4ef"
INK = "#262626"


def report_highlights(markdown: str) -> list[str]:
    """Keep the existing report's current state and next-week observations verbatim."""
    highlights: list[str] = []
    selected = False
    for raw in markdown.splitlines():
        line = raw.strip()
        if line.startswith("#"):
            selected = any(
                label in line for label in ("本周市场背景", "当前状态", "下周观察", "不同计算方法")
            )
        elif line and (selected or line.startswith("数据状态：")):
            highlights.append(re.sub(r"\*\*|`", "", line).removeprefix("- "))
    return highlights


def _wrap(text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for character in text:
        if current and font.getlength(current + character) > width:
            lines.append(current)
            current = ""
        current += character
    if current:
        lines.append(current)
    return lines


def _load_card(path: Path) -> Image.Image:
    with Image.open(path) as source:
        if source.format != "PNG" or source.width * source.height > 20_000_000:
            raise ValueError("weekly card must be a bounded PNG")
        if source.width < WIDTH:
            raise ValueError("weekly card is too narrow for readable single-image delivery")
        source.load()
        card = source.convert("RGB")
    height = round(card.height * WIDTH / card.width)
    return card.resize((WIDTH, height), Image.Resampling.LANCZOS)


def render_weekly_recap(
    *, report: Path, value_card: Path, size_card: Path | None, date: str, out: Path
) -> Path:
    """Reuse validated charts without recalculating or changing their facts."""
    through = datetime.strptime(date, "%Y%m%d").strftime("%Y-%m-%d")
    font = ImageFont.truetype(cjk_font_path(), 27)
    title_font = ImageFont.truetype(cjk_font_path(), 44)
    cards = [_load_card(value_card)]
    if size_card is not None:
        cards.append(_load_card(size_card))
    lines = [
        wrapped
        for item in report_highlights(report.read_text(encoding="utf-8"))
        for wrapped in _wrap(item, font, WIDTH - 120)
    ]
    if not lines:
        raise ValueError("weekly report has no current state or observation highlights")
    footer = "历史统计区间有重叠，独立样本少于周数；研究观察，不构成交易建议。"
    lines.extend(["", *_wrap(footer, font, WIDTH - 120)])
    height = 160 + sum(card.height for card in cards) + 130 + len(lines) * 42
    if height > MAX_HEIGHT:
        raise ValueError("weekly image exceeds readable delivery height")
    image = Image.new("RGB", (WIDTH, height), PAPER)
    draw = ImageDraw.Draw(image)
    draw.text((60, 30), "市场风格周报", fill=INK, font=title_font)
    topics = "价值因子 / 大小盘风格" if size_card is not None else "价值因子"
    draw.text((60, 98), f"数据截至 {through} · {topics}", fill=INK, font=font)
    y = 160
    for card in cards:
        image.paste(card, (0, y))
        y += card.height
    draw.text((60, y + 25), "本期背景、状态与观察", fill=INK, font=title_font)
    for line in lines:
        y += 42
        draw.text((60, y + 70), line, fill=INK, font=font)
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out, format="PNG", optimize=True)
    if out.stat().st_size > MAX_BYTES:
        out.unlink()
        raise ValueError("weekly image exceeds delivery byte limit")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--value-card", type=Path, required=True)
    parser.add_argument("--size-card", type=Path)
    parser.add_argument("--date", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    render_weekly_recap(**vars(args))


if __name__ == "__main__":
    main()
