import json

import numpy as np
import pandas as pd
import pytest
from matplotlib import image as mpimg

from a_share_analysis.size_style_weekly import (
    CROWDING_LOOKBACK_DAYS,
    _prepare_chart_data,
    compute_signal,
    generate_chart,
    load_index_data,
    load_owner_artifact,
    render_markdown,
)


@pytest.fixture()
def index_frames(tmp_path):
    """Write small parquet index files and return a temp dir to scan."""
    dates = pd.bdate_range("2023-01-02", periods=300)
    rng = np.random.default_rng(1)
    data_dir = tmp_path / "index_daily"
    data_dir.mkdir()
    rows = []
    for code, base in (("000300.SH", 3400.0), ("000852.SH", 6200.0)):
        close = base * np.cumprod(1 + rng.normal(0.0, 0.01, len(dates)))
        rows.append(
            pd.DataFrame(
                {
                    "ts_code": code,
                    "trade_date": dates.strftime("%Y%m%d"),
                    "close": close,
                    "amount": rng.uniform(1e8, 9e8, len(dates)),
                }
            )
        )
    pd.concat(rows, ignore_index=True).to_parquet(data_dir / "part.parquet")
    return tmp_path


def test_load_index_data(tmp_path):
    dates = pd.bdate_range("2024-01-01", periods=30)
    frame = pd.DataFrame(
        {
            "ts_code": "SMICRO.TI",
            "trade_date": dates.strftime("%Y%m%d"),
            "close": np.linspace(100, 110, len(dates)),
            "vol": np.linspace(1e7, 2e7, len(dates)),
        }
    )
    data_dir = tmp_path / "index_daily"
    data_dir.mkdir()
    frame.to_parquet(data_dir / "part.parquet")

    monkeypatch = pytest.MonkeyPatch()
    import a_share_analysis.size_style_weekly as mod

    monkeypatch.setattr(mod, "INDEX_DIR", data_dir)
    df = load_index_data("SMICRO.TI")
    monkeypatch.undo()
    assert "amount" in df.columns
    assert "close" in df.columns
    assert len(df) == 30


def test_compute_signal_returns_snapshot(index_frames):
    monkeypatch = pytest.MonkeyPatch()
    import a_share_analysis.size_style_weekly as mod

    monkeypatch.setattr(mod, "INDEX_DIR", index_frames / "index_daily")
    large = load_index_data("000300.SH")
    small = load_index_data("000852.SH")
    snapshot = compute_signal(large, small)
    monkeypatch.undo()

    assert snapshot["as_of"] is not None
    assert 0.0 <= snapshot["small_crowding"] <= 1.0
    assert 0.0 <= snapshot["large_crowding"] <= 1.0
    assert snapshot["crowding_zone"] in ("high_crowding", "low_crowding")


def test_load_owner_artifact_reconstructs_size_style_snapshot(tmp_path):
    path = tmp_path / "size-style.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "research.weekly_analysis.v1",
                "artifact_type": "size_style_weekly",
                "as_of": "20240517",
                "quality": {"status": "passed", "observation_count": 2},
                "snapshot": {
                    "crowding_zone": "low_crowding",
                    "signal": "small_cap",
                    "short_window": 20,
                    "long_window": 60,
                },
                "series": [
                    {"date": "20240516", "small": 0.4, "large": 0.6, "relative_strength": 0.9},
                    {"date": "20240517", "small": 0.5, "large": 0.5, "relative_strength": 1.0},
                ],
            }
        ),
        encoding="utf-8",
    )

    snapshot = load_owner_artifact(path, expected_through="20240517")

    assert snapshot["signal"] == "small_cap"
    assert snapshot["small_series"].iloc[-1] == pytest.approx(0.5)
    assert snapshot["signal"] in ("large_cap", "small_cap", "insufficient")
    assert snapshot["short_window"] in (5, 20)


def _price_frames(dates: pd.DatetimeIndex) -> tuple[pd.DataFrame, pd.DataFrame]:
    large = pd.DataFrame(
        {
            "close": np.linspace(100, 140, len(dates)),
            "amount": np.full(len(dates), 2e8),
        },
        index=dates,
    )
    small = pd.DataFrame(
        {
            "close": np.linspace(120, 100, len(dates)),
            "amount": np.full(len(dates), 1e8),
        },
        index=dates,
    )
    return large, small


def _crowding_history(
    dates: pd.DatetimeIndex,
) -> tuple[pd.Series, pd.Series]:
    small = pd.Series(np.nan, index=dates)
    large = pd.Series(np.nan, index=dates)
    small.iloc[60:] = 0.5
    large.iloc[60:] = 0.5
    return small, large


def test_compute_signal_uses_latest_twenty_valid_crowding_days(monkeypatch):
    import a_share_analysis.size_style_weekly as mod

    dates = pd.bdate_range("2026-01-02", periods=100)
    large, small = _price_frames(dates)
    small_crowding, large_crowding = _crowding_history(dates)
    small_crowding.iloc[-5] = 0.95
    monkeypatch.setattr(
        mod,
        "_crowding_series",
        lambda *_args: (small_crowding, large_crowding),
    )

    snapshot = compute_signal(large, small)

    assert snapshot["crowding_zone"] == "high_crowding"
    assert snapshot["short_window"] == 5
    assert snapshot["long_window"] == 20


def test_compute_signal_rejects_stale_expected_through(monkeypatch):
    import a_share_analysis.size_style_weekly as mod

    dates = pd.bdate_range("2026-01-02", periods=100)
    large, small = _price_frames(dates)
    crowding = _crowding_history(dates)
    monkeypatch.setattr(mod, "_crowding_series", lambda *_args: crowding)
    expected = dates[-1] + pd.offsets.BDay(1)

    with pytest.raises(ValueError, match="size-style data is stale"):
        compute_signal(
            large,
            small,
            expected_through=expected.strftime("%Y%m%d"),
        )


def test_future_observation_does_not_mask_gap_at_expected_through(monkeypatch):
    import a_share_analysis.size_style_weekly as mod

    dates = pd.bdate_range("2026-01-02", periods=100)
    large, small = _price_frames(dates)
    small_crowding, large_crowding = _crowding_history(dates)
    expected = dates[-2]
    small_crowding.loc[expected] = np.nan
    large_crowding.loc[expected] = np.nan
    monkeypatch.setattr(
        mod,
        "_crowding_series",
        lambda *_args: (small_crowding, large_crowding),
    )

    with pytest.raises(ValueError, match=r"actual=.*expected="):
        compute_signal(
            large,
            small,
            expected_through=expected.strftime("%Y%m%d"),
        )


def test_compute_signal_truncates_all_chart_series_at_as_of(monkeypatch):
    import a_share_analysis.size_style_weekly as mod

    dates = pd.bdate_range("2026-01-02", periods=120)
    large, small = _price_frames(dates)
    crowding = _crowding_history(dates)
    monkeypatch.setattr(mod, "_crowding_series", lambda *_args: crowding)
    cutoff = dates[-10]

    snapshot = compute_signal(large, small, as_of=cutoff.strftime("%Y%m%d"))

    assert snapshot["as_of"] == cutoff.date()
    for key in ("small_series", "large_series", "relative_strength"):
        assert snapshot[key].index.max() == cutoff


def test_compute_signal_requires_a_full_crowding_zone_window(monkeypatch):
    import a_share_analysis.size_style_weekly as mod

    dates = pd.bdate_range("2026-01-02", periods=60 + CROWDING_LOOKBACK_DAYS - 1)
    large, small = _price_frames(dates)
    crowding = _crowding_history(dates)
    monkeypatch.setattr(mod, "_crowding_series", lambda *_args: crowding)

    with pytest.raises(ValueError, match="need 20 valid observations"):
        compute_signal(large, small)


def test_generate_chart_matches_weekly_editorial_portrait(monkeypatch, tmp_path):
    import a_share_analysis.size_style_weekly as mod

    dates = pd.bdate_range("2024-01-02", periods=300)
    large, small = _price_frames(dates)
    crowding = _crowding_history(dates)
    monkeypatch.setattr(mod, "_crowding_series", lambda *_args: crowding)
    snapshot = compute_signal(large, small)
    out = tmp_path / "size_style_card.png"

    result = generate_chart(snapshot, out)

    image = mpimg.imread(result)
    assert out.is_file()
    assert image.shape[0] > image.shape[1]
    assert image.shape[0] >= 1400
    assert image.shape[1] >= 1100


def test_generate_chart_uses_compact_research_sections(monkeypatch, tmp_path):
    import a_share_analysis.size_style_weekly as mod

    dates = pd.bdate_range("2024-01-02", periods=300)
    large, small = _price_frames(dates)
    monkeypatch.setattr(mod, "_crowding_series", lambda *_args: _crowding_history(dates))
    snapshot = compute_signal(large, small)
    seen: list[str] = []

    import matplotlib.axes

    original = matplotlib.axes.Axes.set_title
    monkeypatch.setattr(
        matplotlib.axes.Axes,
        "set_title",
        lambda self, label, *args, **kwargs: (seen.append(str(label)), original(self, label, *args, **kwargs))[1],
    )

    generate_chart(snapshot, tmp_path / "size-style.png")

    assert any("方向" in label for label in seen)
    assert any("拥挤风险" in label for label in seen)
    assert not any("看好" in label for label in seen)


def test_chart_aligns_both_lines_as_small_cap_crowding_evidence(monkeypatch):
    import a_share_analysis.size_style_weekly as mod

    dates = pd.bdate_range("2024-01-02", periods=300)
    large, small = _price_frames(dates)
    small_crowding, large_crowding = _crowding_history(dates)
    small_crowding.iloc[-1] = 0.8
    large_crowding.iloc[-1] = 0.05
    monkeypatch.setattr(
        mod,
        "_crowding_series",
        lambda *_args: (small_crowding, large_crowding),
    )
    snapshot = compute_signal(large, small)

    _, recent, _, _, _ = _prepare_chart_data(snapshot, lookback_days=100)

    assert recent["small"].iloc[-1] == pytest.approx(0.8)
    assert recent["large_neglect_confirmation"].iloc[-1] == pytest.approx(0.95)
    assert snapshot["crowding_zone"] == "high_crowding"


def test_render_markdown_contains_key_fields():
    snapshot = {
        "as_of": pd.Timestamp("2026-08-14").date(),
        "small_crowding": 0.4,
        "large_crowding": 0.8,
        "crowding_zone": "low_crowding",
        "signal": "large_cap",
        "short_window": 20,
        "long_window": 60,
        "n_days": 2300,
    }
    md = render_markdown(snapshot)
    assert md.startswith("## 大小盘因子（风格）")
    assert "# 大小盘风格周报" not in md
    assert "低拥挤" in md
    assert "大盘占优" in md
    assert "20 日和 60 日均线" in md
    assert "拥挤程度只影响均线周期" in md
    assert "**" not in md
    assert not any(mark in md for mark in ("“", "”", "；", "——", "(", ")"))
