"""Check that built MkDocs pages display only their language's sidebar."""

import argparse
from pathlib import Path


def primary_navigation(site: Path, path: str) -> str:
    html = (site / path).read_text(encoding="utf-8")
    return html.split("md-sidebar--primary", 1)[1].split("md-sidebar--secondary", 1)[0]


def document_language(site: Path, path: str) -> str:
    html = (site / path).read_text(encoding="utf-8")
    return html.split('<html lang="', 1)[1].split('"', 1)[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site-dir", type=Path, default=Path("site"))
    site = parser.parse_args().site_dir

    assert document_language(site, "index.html") == "en"
    assert document_language(site, "index.zh-CN/index.html") == "zh-CN"
    assert document_language(site, "configuration/index.html") == "en"
    assert document_language(site, "configuration.zh-CN/index.html") == "zh-CN"

    english = primary_navigation(site, "index.html")
    chinese = primary_navigation(site, "index.zh-CN/index.html")
    english_article = primary_navigation(site, "configuration/index.html")
    chinese_article = primary_navigation(site, "configuration.zh-CN/index.html")
    chinese_unsuffixed = primary_navigation(site, "scoring/index.html")
    chinese_boundary = primary_navigation(site, "boundary-contract/index.html")
    english_paired = primary_navigation(site, "scoring.en/index.html")

    for navigation in (english, english_article):
        assert "Getting started" in navigation
        assert "五分钟开始" not in navigation
        assert "简体中文" not in navigation
    for navigation in (chinese, chinese_article):
        assert "五分钟开始" in navigation
        assert "Getting started" not in navigation
        assert "简体中文" not in navigation
    assert "市场日报" in chinese
    assert "Market reports" not in chinese
    for navigation in (chinese_unsuffixed, chinese_boundary):
        assert "五分钟开始" in navigation
        assert "Getting started" not in navigation
        assert "市场日报" in navigation
        assert "Market reports" not in navigation
    assert "Getting started" in english_paired
    assert "五分钟开始" not in english_paired

    english_page = (site / "scoring.en/index.html").read_text(encoding="utf-8")
    assert ">Chinese version<" in english_page
    assert ">中文页面<" not in english_page


if __name__ == "__main__":
    main()
