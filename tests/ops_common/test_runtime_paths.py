from __future__ import annotations

from pathlib import Path

import pytest

from ops_common.paths import resolve_owner_path


def test_owner_path_uses_data_platform_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DATA_PLATFORM_ROOT", str(tmp_path))
    monkeypatch.delenv("A_SHARE_OUTPUT_DIR", raising=False)

    assert (
        resolve_owner_path(
            "market-intel",
            category="reports",
            override_env="A_SHARE_OUTPUT_DIR",
            suffix=("a_share_daily",),
        )
        == tmp_path / "reports/market-intel/a_share_daily"
    )


def test_explicit_owner_path_override_wins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    override = tmp_path / "legacy-compatible-output"
    monkeypatch.setenv("A_SHARE_OUTPUT_DIR", str(override))
    monkeypatch.delenv("DATA_PLATFORM_ROOT", raising=False)
    monkeypatch.delenv("MDP_FALLBACK_ROOT", raising=False)

    assert (
        resolve_owner_path(
            "market-intel",
            category="reports",
            override_env="A_SHARE_OUTPUT_DIR",
            suffix=("a_share_daily",),
        )
        == override
    )


def test_persistent_owner_path_requires_external_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATA_PLATFORM_ROOT", raising=False)
    monkeypatch.delenv("MDP_FALLBACK_ROOT", raising=False)
    monkeypatch.delenv("A_SHARE_OUTPUT_DIR", raising=False)

    with pytest.raises(RuntimeError, match="DATA_PLATFORM_ROOT"):
        resolve_owner_path(
            "market-intel",
            category="reports",
            override_env="A_SHARE_OUTPUT_DIR",
            suffix=("a_share_daily",),
        )


def test_a_share_pipeline_does_not_create_checkout_output_without_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from a_share_daily import pipeline

    monkeypatch.delenv("DATA_PLATFORM_ROOT", raising=False)
    monkeypatch.delenv("MDP_FALLBACK_ROOT", raising=False)
    monkeypatch.delenv("A_SHARE_OUTPUT_DIR", raising=False)
    monkeypatch.setattr(pipeline, "OUTPUT_DIR", pipeline._LEGACY_OUTPUT_DIR)

    with pytest.raises(RuntimeError, match="DATA_PLATFORM_ROOT"):
        pipeline._ensure_output_dir()
