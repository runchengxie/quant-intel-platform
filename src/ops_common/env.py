"""Lightweight .env loader and environment variable helpers.

Merged from tushare-general-data-downloader and tushare-email-fetch.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path


def _env_paths_to_try() -> Iterable[Path]:
    """Yield plausible locations of a .env file."""
    seen: set[Path] = set()

    def maybe(path: Path) -> Iterable[Path]:
        resolved = path.expanduser()
        if resolved in seen:
            return
        seen.add(resolved)
        yield resolved

    cwd = Path.cwd()
    yield from maybe(cwd / ".env")
    yield from maybe(cwd / ".env.local")

    platform_roots: list[Path] = []
    if data_platform_root := os.getenv("DATA_PLATFORM_ROOT"):
        platform_roots.append(Path(data_platform_root))
    # Legacy fallback: a hardcoded sibling-repo path must NEVER be a formal interface.
    # It is only appended when the operator explicitly opts in via MDP_FALLBACK_ROOT,
    # so deployments that rely on a fixed directory layout keep working while new
    # deployments are guided toward the DATA_PLATFORM_ROOT contract.
    if fallback_root := os.getenv("MDP_FALLBACK_ROOT"):
        platform_roots.append(Path(fallback_root))
    for platform_root in platform_roots:
        yield from maybe(platform_root / ".env")
        yield from maybe(platform_root / ".env.local")

    script_dir = Path(__file__).resolve().parent
    for parent in [script_dir, *script_dir.parents]:
        yield from maybe(parent / ".env")
        yield from maybe(parent / ".env.local")


def load_local_env() -> Path | None:
    """Populate os.environ from local .env files without overriding existing values."""
    first_loaded: Path | None = None
    for env_path in _env_paths_to_try():
        if not env_path.exists():
            continue
        first_loaded = first_loaded or env_path
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)
    return first_loaded


def required_env(name: str) -> str:
    """Return env var value or raise SystemExit."""
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def optional_env(name: str, default: str | None = None) -> str | None:
    """Return env var value or default."""
    value = os.getenv(name)
    return value if value else default


def resolve_data_platform_root(*, required: bool = False) -> Path:
    """Resolve an explicitly configured external data root.

    A deployment may opt into ``MDP_FALLBACK_ROOT`` during migration, but the
    public framework never invents a machine-specific ``$HOME`` path.
    """

    raw = os.getenv("DATA_PLATFORM_ROOT", "").strip()
    if not raw:
        raw = os.getenv("MDP_FALLBACK_ROOT", "").strip()
    if raw:
        return Path(raw).expanduser()
    if required:
        raise RuntimeError("DATA_PLATFORM_ROOT must be configured for external data access")
    return Path(".market-intel-external-data-not-configured")


def bool_env(name: str, default: bool = True) -> bool:
    """Return True unless the env var is empty / 'false' / '0' / 'no'."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() not in {"", "false", "0", "no"}
