from __future__ import annotations

from pathlib import Path

import pytest

from ops_common.env import resolve_data_platform_root


def test_data_platform_root_is_required_when_external_data_is_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATA_PLATFORM_ROOT", raising=False)
    monkeypatch.delenv("MDP_FALLBACK_ROOT", raising=False)

    with pytest.raises(RuntimeError, match="DATA_PLATFORM_ROOT"):
        resolve_data_platform_root(required=True)


def test_explicit_root_is_used(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DATA_PLATFORM_ROOT", str(tmp_path))

    assert resolve_data_platform_root(required=True) == tmp_path


def test_explicit_fallback_is_used_only_when_opted_in(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("DATA_PLATFORM_ROOT", raising=False)
    monkeypatch.setenv("MDP_FALLBACK_ROOT", str(tmp_path))

    assert resolve_data_platform_root(required=True) == tmp_path
