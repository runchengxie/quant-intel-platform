from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import yaml

from ops_common.locale import DEFAULT_LOCALE


def test_public_documentation_defaults_to_english() -> None:
    root = Path(__file__).resolve().parents[1]
    config = (root / "mkdocs.yml").read_text(encoding="utf-8")
    assert "language: en" in config
    assert DEFAULT_LOCALE == "en-US"


def test_localized_public_pages_link_to_each_other() -> None:
    root = Path(__file__).resolve().parents[1]
    pairs = (
        ("index.md", "index.zh-CN.md"),
        ("getting-started.md", "getting-started.zh-CN.md"),
        ("concepts.md", "concepts.zh-CN.md"),
        ("architecture.md", "architecture.zh-CN.md"),
        ("data-fetch-architecture.md", "data-fetch-architecture.zh-CN.md"),
        ("contracts.md", "contracts.zh-CN.md"),
        ("configuration.md", "configuration.zh-CN.md"),
        ("how-to/run-daily-report.en.md", "how-to/run-daily-report.md"),
        ("how-to/build-dashboard.en.md", "how-to/build-dashboard.md"),
        ("how-to/market-site.en.md", "how-to/market-site.md"),
        ("how-to/add-data-source.en.md", "how-to/add-data-source.md"),
        ("faq.en.md", "faq.md"),
        ("workflows.en.md", "workflows.md"),
        ("report-structure.en.md", "report-structure.md"),
        ("report-distribution.en.md", "report-distribution.md"),
        ("hotspot-composite.en.md", "hotspot-composite.md"),
        ("hermes-agent-workflow.en.md", "hermes-agent-workflow.md"),
        ("new-machine-setup.en.md", "new-machine-setup.md"),
        ("rate-limits.en.md", "rate-limits.md"),
        ("cli-reference.en.md", "cli-reference.md"),
        ("data-ownership.en.md", "data-ownership.md"),
        ("boundary-contract.en.md", "boundary-contract.md"),
        ("glossary.en.md", "glossary.md"),
        ("public-release/public-boundary.en.md", "public-release/public-boundary.md"),
        (
            "public-release/public-release-checklist.en.md",
            "public-release/public-release-checklist.md",
        ),
        ("public-release/data-provenance.en.md", "public-release/data-provenance.md"),
        ("roadmap.en.md", "roadmap.md"),
        ("web-dashboard.en.md", "web-dashboard.md"),
        ("refactor-plan-etl-report.en.md", "refactor-plan-etl-report.md"),
        ("code-quality-audit-findings.en.md", "code-quality-audit-findings.md"),
        ("a-share-factor-signals.en.md", "a-share-factor-signals.md"),
    )

    for english, chinese in pairs:
        english_page = (root / "docs" / english).read_text(encoding="utf-8")
        chinese_page = (root / "docs" / chinese).read_text(encoding="utf-8")
        assert f"[Chinese version]({Path(chinese).name})" in english_page
        assert f"[English page]({Path(english).name})" in chinese_page


def test_translated_navigation_entries_use_english_canonical_pages() -> None:
    root = Path(__file__).resolve().parents[1]
    config = (root / "mkdocs.yml").read_text(encoding="utf-8")
    assert "Data-fetch architecture: data-fetch-architecture.md" in config
    for page in (
        "how-to/run-daily-report.en.md",
        "how-to/build-dashboard.en.md",
        "how-to/market-site.en.md",
        "how-to/add-data-source.en.md",
        "faq.en.md",
        "workflows.en.md",
        "report-structure.en.md",
        "report-distribution.en.md",
        "hotspot-composite.en.md",
        "hermes-agent-workflow.en.md",
        "new-machine-setup.en.md",
        "rate-limits.en.md",
        "cli-reference.en.md",
        "data-ownership.en.md",
        "boundary-contract.en.md",
        "glossary.en.md",
        "public-release/public-boundary.en.md",
        "public-release/public-release-checklist.en.md",
        "public-release/data-provenance.en.md",
        "roadmap.en.md",
        "web-dashboard.en.md",
        "refactor-plan-etl-report.en.md",
        "code-quality-audit-findings.en.md",
        "a-share-factor-signals.en.md",
    ):
        assert page in config


def test_every_localized_navigation_page_is_listed_in_both_locales() -> None:
    root = Path(__file__).resolve().parents[1]
    docs_root = root / "docs"
    nav = yaml.safe_load((root / "mkdocs.yml").read_text(encoding="utf-8"))["nav"]

    def page_paths(node: object) -> set[str]:
        if isinstance(node, dict):
            return set().union(*(page_paths(value) for value in node.values()))
        if isinstance(node, list):
            return set().union(*(page_paths(value) for value in node))
        if isinstance(node, str) and node.endswith(".md"):
            return {node}
        return set()

    english_paths = page_paths(nav[:-1])
    chinese_paths = page_paths(nav[-1]["简体中文"])
    language_links = (
        (english_paths, chinese_paths, "Chinese version"),
        (chinese_paths, english_paths, "English page"),
    )

    for source_paths, target_paths, label in language_links:
        pattern = re.compile(rf"\[{re.escape(label)}\]\(([^)]+)\)")
        for source in source_paths:
            source_path = docs_root / source
            text = source_path.read_text(encoding="utf-8")
            for match in pattern.finditer(text):
                target = match.group(1).split("#", 1)[0]
                if target.startswith(("https://", "http://")) or not target.endswith(".md"):
                    continue
                target_path = (source_path.parent / target).resolve()
                if not target_path.is_file():
                    continue
                relative_target = target_path.relative_to(docs_root.resolve()).as_posix()
                assert relative_target in target_paths, (
                    f"{source} links to {relative_target}, which is missing from the "
                    f"corresponding locale navigation"
                )


def test_rendered_sidebars_use_the_language_of_each_page(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    site_dir = tmp_path / "site"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mkdocs",
            "build",
            "--strict",
            "--site-dir",
            str(site_dir),
        ],
        cwd=root,
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    def primary_navigation(relative_path: str) -> str:
        html = (site_dir / relative_path).read_text(encoding="utf-8")
        return html.split("md-sidebar--primary", 1)[1].split("md-sidebar--secondary", 1)[0]

    english = primary_navigation("cli-reference.en/index.html")
    chinese = primary_navigation("cli-reference/index.html")
    assert "Common tasks" in english
    assert "CLI reference" in english
    assert "常用任务" not in english
    assert "CLI 参考" not in english
    assert "常用任务" in chinese
    assert "CLI 参考" in chinese
    assert "Common tasks" not in chinese
    assert "CLI reference" not in chinese
