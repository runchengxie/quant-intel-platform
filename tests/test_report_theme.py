from __future__ import annotations

import pytest

from a_share_daily.report_theme import get_report_theme


def test_report_theme_registry_exposes_switchable_report_themes() -> None:
    assert get_report_theme("research_editorial").name == "research_editorial"
    assert get_report_theme("warm_light").surface == "#f4f0e8"
    assert get_report_theme("dark_terminal").surface == "#171717"


def test_report_theme_rejects_unknown_theme() -> None:
    with pytest.raises(ValueError, match="unknown report theme"):
        get_report_theme("not-a-theme")
