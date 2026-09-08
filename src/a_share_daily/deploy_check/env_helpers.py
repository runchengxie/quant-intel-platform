"""Environment helpers for deploy checks."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path

from . import constants as _constants
from .constants import RunFn


def _env_value(env: Mapping[str, str], *names: str) -> str:
    for name in names:
        value = env.get(name, "").strip()
        if value:
            return value
    return ""


def _env_flag(env: Mapping[str, str], name: str, *, default: bool = False) -> bool:
    value = env.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key:
            values[key] = value
    return values


def _default_env(project_root: Path) -> dict[str, str]:
    merged = dict(os.environ)
    stable_dir = Path.home() / ".config/market-intel"
    for env_path in (
        stable_dir / "market-intel.env",
        stable_dir / "market-data-platform.env",
        project_root / ".env",
        project_root / ".env.local",
    ):
        for key, value in _read_env_file(env_path).items():
            merged.setdefault(key, value)
    mdp_dir_raw = merged.get("MDP_DIR", "").strip()
    if mdp_dir_raw:
        for key, value in _read_env_file(Path(mdp_dir_raw).expanduser() / ".env.local").items():
            merged.setdefault(key, value)
    return merged


def _api_key_flags(project_root: Path, env: Mapping[str, str]) -> tuple[bool, bool]:
    glm_ok = bool(_env_value(env, "ZHIPUAI_API_KEY", "GLM_API_KEY", "BIGMODEL_API_KEY"))
    aliyun_ok = bool(
        _env_value(env, "ALIYUN_API_KEY", "DASHSCOPE_API_KEY", "BAILIAN_API_KEY", "QWEN_API_KEY")
    )
    configured_path = env.get("API_KEYS_PATH", "").strip()
    paths = [
        Path(configured_path).expanduser() if configured_path else None,
        project_root / "api_keys.json",
        Path.home() / ".config/market-intel/api_keys.json",
    ]
    seen: set[Path] = set()
    for api_keys_path in paths:
        if api_keys_path is None:
            continue
        api_keys_path = api_keys_path.resolve()
        if api_keys_path in seen or not api_keys_path.exists():
            continue
        seen.add(api_keys_path)
        try:
            payload = json.loads(api_keys_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            payload = {}
        if isinstance(payload, dict):
            keys = {str(key).lower() for key in payload}
            glm_ok = glm_ok or bool(keys & {"zhipu", "glm", "bigmodel", "bigmodel_api_key"})
            aliyun_ok = aliyun_ok or bool(
                keys & {"alibaba_bailian", "aliyun", "dashscope", "qwen", "bailian"}
            )
            ai_news = payload.get("ai_news")
            if isinstance(ai_news, dict):
                provider = str(ai_news.get("provider", "")).lower()
                configured_keys = ai_news.get("keys")
                if isinstance(configured_keys, list) and configured_keys:
                    glm_ok = glm_ok or provider in {"glm", "zhipu", "bigmodel", "zhipuai"}
    return glm_ok, aliyun_ok


def _safe_run(run: RunFn, cmd: Sequence[str]) -> _constants.CompletedProcess[str] | None:
    try:
        return run(cmd, capture_output=True, text=True, timeout=10, check=False)
    except Exception:
        return None
