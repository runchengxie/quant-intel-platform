from pathlib import Path

from ops_common import env


def test_load_local_env_reads_all_candidate_files_without_overriding(
    tmp_path: Path, monkeypatch
) -> None:
    # Keep variables populated by ``load_local_env`` inside this test.  The
    # loader intentionally mutates ``os.environ`` directly, so an isolated
    # mapping prevents local .env values from leaking into later tests.
    monkeypatch.setattr(env.os, "environ", dict(env.os.environ))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    project_root = tmp_path / "project"
    platform_root = tmp_path / "market-data-platform"
    package_root = tmp_path / "src" / "ops_common"
    project_root.mkdir()
    platform_root.mkdir()
    package_root.mkdir(parents=True)

    (project_root / ".env").write_text(
        "SHARED=project\nPROJECT_ONLY=one\nexport EXPORTED=yes\n",
        encoding="utf-8",
    )
    (project_root / ".env.local").write_text(
        "SHARED=project_local\nLOCAL_ONLY=two\n",
        encoding="utf-8",
    )
    (platform_root / ".env.local").write_text(
        "PLATFORM_ONLY=three\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(project_root)
    monkeypatch.setenv("DATA_PLATFORM_ROOT", str(platform_root))
    monkeypatch.setenv("SHARED", "existing")
    monkeypatch.setattr(env, "__file__", str(package_root / "env.py"))

    first_loaded = env.load_local_env()

    assert first_loaded == project_root / ".env"
    assert env.os.environ["SHARED"] == "existing"
    assert env.os.environ["PROJECT_ONLY"] == "one"
    assert env.os.environ["EXPORTED"] == "yes"
    assert env.os.environ["LOCAL_ONLY"] == "two"
    assert env.os.environ["PLATFORM_ONLY"] == "three"
