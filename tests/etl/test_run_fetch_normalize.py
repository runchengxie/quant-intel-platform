"""冒烟测试：事件规范化相关的纯函数。

这些函数原在 run_fetch.py，已拆分到 `daily_messenger.etl.fetchers.normalize`。
无网络、无 IO 依赖，是拆分后的回归安全网。
"""

import importlib
import json
import sys

import pytest

from daily_messenger.etl.fetchers.normalize import (
    EVENT_METADATA_FIELDS,
    _append_source_chain_entry,
    _clean_event_text,
    _normalize_raw_event,
    _normalize_raw_events_payload,
    _valid_event_url,
)


@pytest.fixture
def load_run_fetch(monkeypatch):
    """动态导入 run_fetch 模块，隔离 API 环境变量。"""

    def _loader(api_keys):
        if api_keys is None:
            monkeypatch.delenv("API_KEYS", raising=False)
        else:
            monkeypatch.setenv("API_KEYS", json.dumps(api_keys))
        module_name = "daily_messenger.etl.run_fetch"
        if module_name in sys.modules:
            return importlib.reload(sys.modules[module_name])
        return importlib.import_module(module_name)

    return _loader


def test_safe_float_accepts_numbers(load_run_fetch):
    module = load_run_fetch({})
    assert module._safe_float("1.5") == 1.5
    assert module._safe_float(3) == 3.0


def test_safe_float_returns_none_on_garbage(load_run_fetch):
    module = load_run_fetch({})
    assert module._safe_float("not-a-number") is None
    assert module._safe_float(None) is None


def test_clean_event_text_normalizes_whitespace():
    assert _clean_event_text(123) == ""
    assert _clean_event_text("a" * 500, max_len=10) == "a" * 10


def test_valid_event_url():
    assert _valid_event_url("https://example.com")
    assert _valid_event_url("http://example.com")
    assert not _valid_event_url("ftp://example.com")
    assert not _valid_event_url("example.com")


def test_append_source_chain_entry_dedups():
    chain: list[dict[str, str]] = []
    _append_source_chain_entry(chain, source="Reuters", url="https://reuters.com/a")
    _append_source_chain_entry(chain, source="Reuters", url="https://reuters.com/a")
    assert len(chain) == 1
    _append_source_chain_entry(chain, source="Bloomberg", url="https://bloomberg.com/b")
    assert len(chain) == 2


def test_append_source_chain_entry_drops_invalid_url():
    chain: list[dict[str, str]] = []
    _append_source_chain_entry(chain, source="X", url="not-a-url")
    # 无效 url 被清空，但 source 仍保留
    assert chain == [{"source": "X", "url": ""}]


def test_normalize_raw_event_requires_title():
    assert _normalize_raw_event({"url": "https://example.com"}) is None


def test_normalize_raw_event_keeps_metadata():
    entry = {
        "title": "Fed holds rates",
        "url": "https://example.com/fed",
        "impact": "high",
        "country": "US",
    }
    normalized = _normalize_raw_event(entry)
    assert normalized is not None
    assert normalized["title"] == "Fed holds rates"
    assert normalized["url"] == "https://example.com/fed"
    assert normalized["impact"] == "high"


def test_normalize_raw_event_drops_invalid_url():
    entry = {"title": "Headline", "url": "ftp://bad"}
    normalized = _normalize_raw_event(entry)
    assert normalized is not None
    assert "url" not in normalized


def test_normalize_raw_events_payload_skips_empty():
    events = [{"title": "A"}, {"url": "https://x.com"}]  # 第二个无 title
    ai_updates = [{"title": "B", "provider": "glm"}]
    normalized_events, normalized_ai = _normalize_raw_events_payload(events, ai_updates)
    assert len(normalized_events) == 1
    assert normalized_events[0]["title"] == "A"
    assert len(normalized_ai) == 1
    assert normalized_ai[0]["source"] == "glm"


def test_event_metadata_fields_is_set():
    assert isinstance(EVENT_METADATA_FIELDS, set)
    assert "title" in EVENT_METADATA_FIELDS
