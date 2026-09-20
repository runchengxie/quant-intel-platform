"""Shared report themes, independent from report content and delivery."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReportTheme:
    name: str
    label: str
    surface: str
    panel: str
    ink: str
    muted: str
    accent: str
    rule: str


REPORT_THEMES = {
    "research_editorial": ReportTheme(
        name="research_editorial",
        label="研究编辑部",
        surface="#f4f0e8",
        panel="#f8f5ef",
        ink="#252525",
        muted="#81796e",
        accent="#b64d33",
        rule="#d8d0c4",
    ),
    "warm_light": ReportTheme(
        name="warm_light",
        label="暖白简报",
        surface="#f4f0e8",
        panel="#fbfaf7",
        ink="#252525",
        muted="#81796e",
        accent="#c84b2f",
        rule="#d8d0c4",
    ),
    "dark_terminal": ReportTheme(
        name="dark_terminal",
        label="深色终端",
        surface="#171717",
        panel="#222222",
        ink="#f2efe8",
        muted="#aaa39a",
        accent="#ef8a5b",
        rule="#454545",
    ),
}


def get_report_theme(name: str | None = None) -> ReportTheme:
    selected = (name or "research_editorial").strip().lower()
    try:
        return REPORT_THEMES[selected]
    except KeyError as exc:
        choices = ", ".join(REPORT_THEMES)
        raise ValueError(f"unknown report theme {name!r}; choose one of: {choices}") from exc


__all__ = ["REPORT_THEMES", "ReportTheme", "get_report_theme"]
