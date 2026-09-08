"""Pipeline and Hermes script checks for deploy checks."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from . import constants as _constants
from .constants import HERMES_SCRIPT_NAMES, SCRIPT_NAMES, CheckResult


def _check_scripts(project_root: Path) -> CheckResult:
    missing: list[str] = []
    not_executable: list[str] = []
    for name in SCRIPT_NAMES:
        path = project_root / "scripts" / name
        if not path.exists():
            missing.append(name)
        elif not os.access(path, os.X_OK):
            not_executable.append(name)
    if missing:
        return _constants._result("pipeline scripts", "fail", f"缺少脚本: {', '.join(missing)}")
    if not_executable:
        return _constants._result(
            "pipeline scripts", "warn", f"未设置可执行权限: {', '.join(not_executable)}"
        )
    return _constants._result("pipeline scripts", "ok", "晨报、晚报和补抓脚本都存在且可执行")


def _check_hermes_script_files(project_root: Path, env: Mapping[str, str]) -> CheckResult:
    hermes_home = Path(env.get("HERMES_HOME", str(Path.home() / ".hermes"))).expanduser()
    scripts_dir = Path(env.get("HERMES_SCRIPTS_DIR", str(hermes_home / "scripts"))).expanduser()
    missing: list[str] = []
    escaped: list[str] = []
    not_executable: list[str] = []
    stale: list[str] = []
    scripts_dir_resolved = scripts_dir.resolve()

    for name in HERMES_SCRIPT_NAMES:
        path = scripts_dir / name
        if not path.exists():
            missing.append(name)
            continue
        real_path = path.resolve()
        if path.is_symlink() or scripts_dir_resolved not in (real_path, *real_path.parents):
            escaped.append(name)
            continue
        if not os.access(path, os.X_OK):
            not_executable.append(name)
        source = project_root / "scripts" / name
        if source.is_file() and source.read_bytes() != path.read_bytes():
            stale.append(name)

    if escaped:
        return _constants._result(
            "Hermes script files",
            "fail",
            f"脚本为 symlink 或真实路径逃出 {scripts_dir}: {', '.join(escaped)}",
        )
    if missing:
        return _constants._result(
            "Hermes script files", "warn", f"缺少 Hermes/systemd 脚本: {', '.join(missing)}"
        )
    if not_executable:
        return _constants._result(
            "Hermes script files", "warn", f"未设置可执行权限: {', '.join(not_executable)}"
        )
    if stale:
        return _constants._result(
            "Hermes script files",
            "fail",
            f"Hermes 脚本不是仓库当前版本: {', '.join(stale)}。运行 scripts/setup_cron.sh --layer3",
        )
    return _constants._result(
        "Hermes script files", "ok", "Hermes/systemd 脚本均为目录内实体文件且与仓库一致"
    )
