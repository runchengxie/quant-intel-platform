"""Show only the navigation matching the current document language."""

from __future__ import annotations

from copy import copy
from pathlib import Path

from mkdocs.structure.nav import Navigation

LINK_TITLES = {"Daily site": "日报网站"}


def _is_chinese(page) -> bool:
    source = page.file.src_uri
    if source.endswith(".zh-CN.md"):
        return True
    if source.endswith(".en.md"):
        return False
    if source.endswith(".md"):
        english_pair = page.file.abs_src_path[:-3] + ".en.md"
        return Path(english_pair).is_file()
    return False


def _for_locale(items, chinese: bool):
    selected = []
    for item in items:
        if item.is_page:
            if _is_chinese(item) == chinese:
                selected.append(item)
        elif item.is_section:
            children = _for_locale(item.children, chinese)
            if children:
                section = copy(item)
                section.children = children
                selected.append(section)
        elif item.is_link:
            link = copy(item)
            if chinese:
                link.title = LINK_TITLES.get(link.title, link.title)
            selected.append(link)
    return selected


def on_page_context(context, page, config, nav):
    chinese = _is_chinese(page)
    items = _for_locale(nav.items, chinese)
    flattened = []
    for item in items:
        if item.is_section and item.title in {"English", "简体中文"}:
            flattened.extend(item.children)
        else:
            flattened.append(item)
    pages = [item for item in nav.pages if _is_chinese(item) == chinese]
    context["nav"] = Navigation(flattened, pages)
    return context
