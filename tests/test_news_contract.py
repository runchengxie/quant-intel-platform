import json
from datetime import UTC, datetime

import requests

from daily_messenger.common.news_contract import (
    normalize_news_items,
    parse_news_items_from_text,
    render_news_text,
)
from daily_messenger.etl.fetchers import ai_news


def test_news_contract_filters_items_without_auditable_source() -> None:
    payload = {
        "items": [
            {
                "category": "policy",
                "title": "政策发布",
                "summary": "监管部门发布新的市场制度安排。",
                "source": "证监会",
                "url": "https://example.com/policy",
                "published_at": "2026-06-30",
            },
            {
                "category": "sector",
                "title": "无链接消息",
                "summary": "这条消息没有可审计链接。",
                "source": "某媒体",
                "published_at": "2026-06-30",
            },
        ]
    }

    raw_items = parse_news_items_from_text(f"<news_json>{json.dumps(payload)}</news_json>")
    items, errors = normalize_news_items(raw_items, market="cn", label="A股")

    assert len(items) == 1
    assert items[0]["title"] == "政策发布"
    assert errors and "url" in errors[0]
    rendered = render_news_text(items)
    assert "证监会" in rendered
    assert "无链接消息" not in rendered


def test_ai_news_payload_reuses_structured_fetcher(monkeypatch) -> None:
    def fake_glm_call(*_args, **_kwargs):
        payload = {
            "items": [
                {
                    "category": "macro",
                    "title": "宏观数据发布",
                    "summary": "官方发布新的宏观数据。",
                    "source": "统计部门",
                    "url": "https://news.test/macro",
                    "published_at": "2026-06-30",
                }
            ]
        }
        return {
            "choices": [
                {
                    "message": {
                        "content": f"<news_json>{json.dumps(payload)}</news_json>",
                    }
                }
            ]
        }

    monkeypatch.setattr(ai_news, "_call_glm_chat_completions", fake_glm_call)
    monkeypatch.setattr(ai_news, "THROTTLE_DISABLED", True)

    result = ai_news.fetch_market_news_payload(
        ["cn"],
        api_keys={"ai_news": {"provider": "glm", "keys": ["test-key"], "glm_model": "glm-test"}},
        now_utc=datetime(2026, 6, 30, 8, tzinfo=UTC),
    )

    assert result["markets_requested"] == ["cn"]
    assert list(result["markets"]) == ["cn"]
    entry = result["markets"]["cn"]
    assert entry["model"] == "glm-test"
    assert entry["items"][0]["url"] == "https://news.test/macro"
    assert "官方发布新的宏观数据" in entry["news_text"]


def test_ai_news_settings_chain_auto_adds_aliyun_top_level_key() -> None:
    settings = ai_news._resolve_ai_news_settings_chain(
        {
            "ai_news": {
                "provider": "glm",
                "keys": ["glm-key"],
                "aliyun_model": "qwen-test",
            },
            "alibaba_bailian": "aliyun-key",
        }
    )

    assert [item.provider for item in settings] == ["glm", "aliyun"]
    assert settings[1].model == "qwen-test"
    assert settings[1].keys == [("alibaba_bailian", "aliyun-key")]


def test_ai_news_payload_falls_back_to_aliyun(monkeypatch) -> None:
    def fake_glm_call(*_args, **_kwargs):
        raise requests.HTTPError("glm quota exceeded")

    def fake_aliyun_call(
        model,
        api_key,
        prompt,
        enable_network,
        timeout,
        base_url,
        search_strategy,
        direct_connection,
    ):
        assert model == "qwen-test"
        assert api_key == "aliyun-key"
        assert enable_network is True
        assert search_strategy == "turbo"
        assert direct_connection is True
        assert "<news>" in prompt
        payload = {
            "items": [
                {
                    "category": "sector",
                    "title": "产业消息",
                    "summary": "产业链发布新的市场动态。",
                    "source": "产业媒体",
                    "url": "https://news.test/sector",
                    "published_at": "2026-06-30",
                }
            ]
        }
        return {
            "choices": [
                {
                    "message": {
                        "content": f"<news>{json.dumps(payload, ensure_ascii=False)}</news>",
                    }
                }
            ]
        }

    monkeypatch.setattr(ai_news, "_call_glm_chat_completions", fake_glm_call)
    monkeypatch.setattr(ai_news, "_call_aliyun_chat_completions", fake_aliyun_call)
    monkeypatch.setattr(ai_news, "THROTTLE_DISABLED", True)

    result = ai_news.fetch_market_news_payload(
        ["cn"],
        api_keys={
            "ai_news": {
                "provider": "glm",
                "keys": ["glm-key"],
                "glm_model": "glm-test",
                "aliyun_model": "qwen-test",
            },
            "alibaba_bailian": "aliyun-key",
        },
        now_utc=datetime(2026, 6, 30, 8, tzinfo=UTC),
    )

    entry = result["markets"]["cn"]
    assert entry["provider"] == "aliyun_bailian"
    assert entry["model"] == "qwen-test"
    assert entry["items"][0]["url"] == "https://news.test/sector"
    assert entry["fallback_errors"]


def test_ai_news_filters_placeholder_urls_and_market_drift() -> None:
    items, errors = ai_news._filter_market_relevant_items(
        [
            {
                "market": "jp",
                "label": "日股",
                "category": "macro",
                "title": "OPEC+拟增产",
                "summary": "OPEC+成员国计划提高石油产量目标。",
                "source": "期货日报",
                "url": "https://news.test/oil",
                "published_at": "2026-07-02",
            },
            {
                "market": "jp",
                "label": "日股",
                "category": "sector",
                "title": "日经下跌，东京电子承压",
                "summary": "日本半导体股跟随美股回调，东京电子跌幅居前。",
                "source": "财经媒体",
                "url": "https://news.test/japan-semis",
                "published_at": "2026-07-02",
            },
            {
                "market": "jp",
                "label": "日股",
                "category": "sector",
                "title": "示例链接",
                "summary": "日本市场新闻但链接为占位来源。",
                "source": "示例媒体",
                "url": "https://example.com/japan",
                "published_at": "2026-07-02",
            },
        ],
        market="jp",
    )

    assert [item["title"] for item in items] == ["日经下跌，东京电子承压"]
    assert any("market relevance" in error for error in errors)
    assert any("placeholder source URL" in error for error in errors)
