"""Deployment health checks for owner-managed TuShare credentials."""

from __future__ import annotations

import os
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

CredentialStatus = Literal["ok", "warn", "fail"]


def _configured(env: Mapping[str, str], name: str) -> bool:
    return bool(env.get(name, "").strip())


def selected_provider_json(env: Mapping[str, str]) -> Path | None:
    """Select a path for metadata checks without parsing owner credentials."""
    if "DATA_PLATFORM_CONFIG" in env:
        return Path(env["DATA_PLATFORM_CONFIG"]).expanduser().absolute()
    home = Path(env.get("HOME") or Path.home())
    root = Path(env.get("XDG_CONFIG_HOME") or home / ".config")
    path = root / "quant-market-data-platform/config.json"
    return path if path.exists() or path.is_symlink() else None


def _credential_file_issue(env: Mapping[str, str]) -> str | None:
    selected = selected_provider_json(env)
    if "DATA_PLATFORM_CONFIG" in env and not env["DATA_PLATFORM_CONFIG"].strip():
        return "DATA_PLATFORM_CONFIG 必须指定私有 JSON 文件"
    path = (
        selected
        or Path.home() / ".config/richard/projects/quant/quant-market-data-platform/config.env"
    )
    if selected is None and not path.exists():
        return None
    try:
        metadata = path.lstat()
    except OSError:
        return "无法读取市场数据凭证文件元数据，请检查 DATA_PLATFORM_CONFIG"
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        return "TuShare 凭证文件必须是普通非 symlink 文件"
    if os.name == "nt":
        return None
    if stat.S_IMODE(metadata.st_mode) != 0o600:
        return "TuShare 凭证文件权限必须精确为 0600"
    if hasattr(os, "geteuid") and metadata.st_uid != os.geteuid():
        return "TuShare 凭证文件必须属于当前用户"
    return None


def credential_health(env: Mapping[str, str]) -> tuple[CredentialStatus, str]:
    """Describe a proxy-first credential chain without exposing any value."""

    if issue := _credential_file_issue(env):
        return "fail", issue
    proxy_token = _configured(env, "TUSHARE_TOKEN_2")
    proxy_url = _configured(env, "TUSHARE_API_URL_2")
    fallback_token = _configured(env, "TUSHARE_TOKEN")
    if proxy_token and not proxy_url and not fallback_token:
        return (
            "fail",
            "已配置 TUSHARE_TOKEN_2，但缺少配套 TUSHARE_API_URL_2，且没有 TUSHARE_TOKEN 兜底",
        )
    if not (proxy_token and proxy_url) and not fallback_token:
        return (
            "warn",
            "未检测到可用凭证；请通过 owner 的 marketdata config run 使用 DATA_PLATFORM_CONFIG "
            "指定的私有 JSON，配置 TOKEN_2+URL_2，并保留 TOKEN 兜底",
        )

    if proxy_token and proxy_url and fallback_token:
        return (
            "ok",
            "已配置 TOKEN_2+URL_2 主通道及 TOKEN 兜底；凭证由 quant-market-data-platform 管理",
        )
    if proxy_token and proxy_url:
        return "warn", "已配置 TOKEN_2+URL_2，但缺少 TUSHARE_TOKEN 兜底"
    detail = "仅配置 TUSHARE_TOKEN 低权限通道"
    if proxy_token:
        detail += "；TOKEN_2 因缺少 URL_2 不可用"
    return "warn", detail


__all__ = ["CredentialStatus", "credential_health"]
