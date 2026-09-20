from __future__ import annotations

import matplotlib.pyplot as plt
from matplotlib.colors import to_rgb

from a_share_daily.charts.theme import (
    BLUE_SCALE,
    LIGHT,
    add_report_header,
    apply_editorial_background,
    apply_graph_paper,
)


def test_editorial_blue_scale_starts_at_the_primary_accent() -> None:
    assert BLUE_SCALE[0] == LIGHT.ACCENT
    assert len(BLUE_SCALE) >= 5
    assert len(set(BLUE_SCALE)) == len(BLUE_SCALE)


def test_editorial_background_is_idempotent_and_does_not_add_axes() -> None:
    fig = plt.figure(figsize=(4, 3))
    try:
        apply_editorial_background(fig)
        artist_count = len(fig.artists)
        apply_editorial_background(fig)

        assert fig.axes == []
        assert len(fig.artists) == artist_count
        assert fig.get_facecolor()[:3] == to_rgb(LIGHT.BG)
    finally:
        plt.close(fig)


def test_editorial_background_is_quiet_by_default_and_graph_paper_is_explicit() -> None:
    fig = plt.figure(figsize=(4, 3))
    graph_fig = plt.figure(figsize=(4, 3))
    try:
        apply_editorial_background(fig)
        quiet_artist_count = len(fig.artists)
        apply_graph_paper(graph_fig)
        assert len(graph_fig.artists) > quiet_artist_count
    finally:
        plt.close(fig)
        plt.close(graph_fig)


def test_report_header_uses_editorial_hierarchy() -> None:
    fig = plt.figure(figsize=(4, 3))
    try:
        add_report_header(
            fig,
            title="本周市场复盘",
            kicker="08/03–08/07 · A股周报",
            subtitle="5 个交易日 · 5 天上涨",
        )

        rendered = {text.get_text(): text for text in fig.texts}
        assert (
            rendered["本周市场复盘"].get_fontsize()
            > rendered["5 个交易日 · 5 天上涨"].get_fontsize()
        )
        assert rendered["08/03–08/07 · A股周报"].get_color() == LIGHT.ACCENT
        assert fig.axes == []
    finally:
        plt.close(fig)
