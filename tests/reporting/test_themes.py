from __future__ import annotations

import pytest

from a_share_daily.reporting.themes import available_themes, get_theme


def test_three_report_themes_are_available() -> None:
    assert available_themes() == ("dark_terminal", "research_editorial", "warm_light")
    assert get_theme("research_editorial").tokens["surface"] == "#f4f0e8"


def test_unknown_theme_lists_valid_choices() -> None:
    with pytest.raises(ValueError, match="dark_terminal"):
        get_theme("unknown")
