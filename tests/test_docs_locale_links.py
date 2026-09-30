from __future__ import annotations

from pathlib import Path

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
    )

    for english, chinese in pairs:
        english_page = (root / "docs" / english).read_text(encoding="utf-8")
        chinese_page = (root / "docs" / chinese).read_text(encoding="utf-8")
        assert f"[中文页面]({Path(chinese).name})" in english_page
        assert f"[English page]({Path(english).name})" in chinese_page


def test_translated_navigation_entries_use_english_canonical_pages() -> None:
    root = Path(__file__).resolve().parents[1]
    config = (root / "mkdocs.yml").read_text(encoding="utf-8")
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
    ):
        assert page in config
