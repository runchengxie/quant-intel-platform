"""Theme registry for report renderers."""

from __future__ import annotations

from dataclasses import dataclass

from ..report_theme import REPORT_THEMES


@dataclass(frozen=True)
class ReportTheme:
    name: str
    tokens: dict[str, str]
    layout: dict[str, float]
    renderer_capabilities: frozenset[str]


def _theme(name: str) -> ReportTheme:
    source = REPORT_THEMES[name]
    return ReportTheme(
        name=name,
        tokens={
            "surface": source.surface,
            "panel": source.panel,
            "ink": source.ink,
            "muted": source.muted,
            "accent": source.accent,
            "rule": source.rule,
        },
        layout={"margin": 0.055, "header_height": 0.17},
        renderer_capabilities=frozenset({"markdown", "png"}),
    )


THEMES = {name: _theme(name) for name in REPORT_THEMES}


def get_theme(name: str) -> ReportTheme:
    selected = name.strip().lower()
    try:
        return THEMES[selected]
    except KeyError as exc:
        raise ValueError(
            f"unknown report theme {name!r}; choose one of: {', '.join(available_themes())}"
        ) from exc


def available_themes() -> tuple[str, ...]:
    return tuple(sorted(THEMES))


__all__ = ["ReportTheme", "THEMES", "available_themes", "get_theme"]
