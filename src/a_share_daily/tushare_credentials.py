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


def _credential_file_issue(env: Mapping[str, str]) -> str | None:
    raw = env.get("MDP_DIR", "").strip()
    if not raw:
        return None
    mdp_dir = Path(raw).expanduser()
    path = mdp_dir / ".env.local"
    if not path.exists():
        return None
    try:
        metadata = path.lstat()
    except OSError:
        return "无法读取 market-data-platform/.env.local 元数据"
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
            "未检测到可用凭证；在 market-data-platform/.env.local 配置 TOKEN_2+URL_2，并保留 TOKEN 兜底",
        )

    if issue := _credential_file_issue(env):
        return "fail", issue
    if proxy_token and proxy_url and fallback_token:
        return (
            "ok",
            "已配置 TOKEN_2+URL_2 主通道及 TOKEN 兜底；凭证由 market-data-platform 管理",
        )
    if proxy_token and proxy_url:
        return "warn", "已配置 TOKEN_2+URL_2，但缺少 TUSHARE_TOKEN 兜底"
    detail = "仅配置 TUSHARE_TOKEN 低权限通道"
    if proxy_token:
        detail += "；TOKEN_2 因缺少 URL_2 不可用"
    return "warn", detail


__all__ = ["CredentialStatus", "credential_health"]
