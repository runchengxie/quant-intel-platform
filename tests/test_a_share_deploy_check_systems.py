from __future__ import annotations

import subprocess
from pathlib import Path

from a_share_daily.deploy_check import (
    HERMES_GATEWAY_PREFLIGHT_TIMER,
    HERMES_GATEWAY_SERVICE,
    SYSTEMD_TIMERS,
    WINDOWS_TASKS,
    _check_hermes_gateway_systemd,
    _check_lark_cli,
    _check_systemd,
    _check_windows_tasks,
)


def test_lark_cli_check_detects_scoop_persist_config(tmp_path: Path) -> None:
    scoop_root = tmp_path / "scoop"
    cli_path = scoop_root / "shims" / "lark-cli.exe"
    config_path = scoop_root / "persist" / "lark-cli" / "hermes" / "config.json"
    cli_path.parent.mkdir(parents=True)
    config_path.parent.mkdir(parents=True)
    cli_path.write_text("", encoding="utf-8")
    config_path.write_text("{}", encoding="utf-8")

    result = _check_lark_cli(
        {"LARK_CLI": str(cli_path), "SCOOP": str(scoop_root)},
        which=lambda _name: None,
    )

    assert result.status == "ok"


def test_systemd_check_uses_unit_files_when_user_bus_is_blocked(tmp_path: Path) -> None:
    wants_dir = tmp_path / "config" / "systemd" / "user" / "timers.target.wants"
    wants_dir.mkdir(parents=True)
    for timer in SYSTEMD_TIMERS:
        (wants_dir / timer).write_text("", encoding="utf-8")

    def fake_run(
        cmd: list[str],
        capture_output: bool = False,
        text: bool = False,
        timeout: int | None = None,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            cmd,
            1,
            "",
            "Failed to connect to user scope bus via local transport: Operation not permitted",
        )

    result = _check_systemd(
        {"XDG_CONFIG_HOME": str(tmp_path / "config")},
        which=lambda name: "/usr/bin/systemctl" if name == "systemctl" else None,
        run=fake_run,
    )

    assert result.status == "ok"
    assert "unit 文件确认" in result.detail


def test_systemd_check_warns_when_an_enabled_service_is_failed() -> None:
    def fake_run(
        cmd: list[str],
        capture_output: bool = False,
        text: bool = False,
        timeout: int | None = None,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        if cmd[2:4] == ["show", "--property=LoadState,ActiveState"]:
            return subprocess.CompletedProcess(cmd, 0, "loaded\nfailed\n", "")
        return subprocess.CompletedProcess(cmd, 0, "enabled\n", "")

    result = _check_systemd(
        {},
        which=lambda name: "/usr/bin/systemctl" if name == "systemctl" else None,
        run=fake_run,
    )

    assert result.status == "warn"
    assert "service failed" in result.detail


def test_gateway_systemd_check_requires_loaded_enabled_active_units() -> None:
    commands: list[tuple[str, ...]] = []

    def fake_run(
        cmd: list[str],
        capture_output: bool = False,
        text: bool = False,
        timeout: int | None = None,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        commands.append(tuple(cmd))
        stdout = "loaded\n" if "show" in cmd else ""
        return subprocess.CompletedProcess(cmd, 0, stdout, "")

    result = _check_hermes_gateway_systemd(
        which=lambda name: "/usr/bin/systemctl" if name == "systemctl" else None,
        run=fake_run,
    )

    assert result.status == "ok"
    for unit in (HERMES_GATEWAY_SERVICE, HERMES_GATEWAY_PREFLIGHT_TIMER):
        assert (
            "systemctl",
            "--user",
            "show",
            "--property=LoadState",
            "--value",
            unit,
        ) in commands
        assert ("systemctl", "--user", "is-enabled", unit) in commands
        assert ("systemctl", "--user", "is-active", "--quiet", unit) in commands


def test_gateway_systemd_check_warns_when_service_is_not_installed() -> None:
    def fake_run(
        cmd: list[str],
        capture_output: bool = False,
        text: bool = False,
        timeout: int | None = None,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        if "show" in cmd and cmd[-1] == HERMES_GATEWAY_SERVICE:
            return subprocess.CompletedProcess(cmd, 0, "not-found\n", "")
        stdout = "loaded\n" if "show" in cmd else ""
        return subprocess.CompletedProcess(cmd, 0, stdout, "")

    result = _check_hermes_gateway_systemd(
        which=lambda name: "/usr/bin/systemctl" if name == "systemctl" else None,
        run=fake_run,
    )

    assert result.status == "warn"
    assert "Gateway service 未安装" in result.detail


def test_gateway_systemd_check_warns_for_disabled_or_inactive_units() -> None:
    def fake_run(
        cmd: list[str],
        capture_output: bool = False,
        text: bool = False,
        timeout: int | None = None,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        if "show" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "loaded\n", "")
        if "is-enabled" in cmd and cmd[-1] == HERMES_GATEWAY_SERVICE:
            return subprocess.CompletedProcess(cmd, 1, "disabled\n", "")
        if "is-active" in cmd and cmd[-1] == HERMES_GATEWAY_PREFLIGHT_TIMER:
            return subprocess.CompletedProcess(cmd, 3, "inactive\n", "")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    result = _check_hermes_gateway_systemd(
        which=lambda name: "/usr/bin/systemctl" if name == "systemctl" else None,
        run=fake_run,
    )

    assert result.status == "warn"
    assert "Gateway service 未启用" in result.detail
    assert "Gateway preflight timer 未运行" in result.detail


def test_windows_task_check_reports_existing_tasks() -> None:
    def fake_run(
        cmd: list[str],
        capture_output: bool = False,
        text: bool = False,
        timeout: int | None = None,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        assert cmd[0] == "schtasks"
        assert cmd[3] in WINDOWS_TASKS
        return subprocess.CompletedProcess(cmd, 0, "", "")

    result = _check_windows_tasks(fake_run)

    assert result.status == "ok"


def test_windows_task_check_warns_when_task_missing() -> None:
    def fake_run(
        cmd: list[str],
        capture_output: bool = False,
        text: bool = False,
        timeout: int | None = None,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 1, "", "ERROR")

    result = _check_windows_tasks(fake_run)

    assert result.status == "warn"
    assert "install_scheduled_tasks.ps1" in result.detail
