"""Check that built MkDocs pages display only their language's sidebar."""

import argparse
from pathlib import Path


def primary_navigation(site: Path, path: str) -> str:
    html = (site / path).read_text(encoding="utf-8")
    return html.split("md-sidebar--primary", 1)[1].split("md-sidebar--secondary", 1)[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site-dir", type=Path, default=Path("site"))
    site = parser.parse_args().site_dir

    english = primary_navigation(site, "index.html")
    chinese = primary_navigation(site, "index.zh-CN/index.html")
    english_article = primary_navigation(site, "configuration/index.html")
    chinese_article = primary_navigation(site, "configuration.zh-CN/index.html")

    for navigation in (english, english_article):
        assert "Getting started" in navigation
        assert "五分钟开始" not in navigation
        assert "简体中文" not in navigation
    for navigation in (chinese, chinese_article):
        assert "五分钟开始" in navigation
        assert "Getting started" not in navigation
        assert "简体中文" not in navigation
    assert "日报网站" in chinese
    assert "Daily site" not in chinese


if __name__ == "__main__":
    main()
