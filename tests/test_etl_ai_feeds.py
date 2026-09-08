import importlib
import json
import sys
from datetime import UTC, datetime

import pytest
import requests

from daily_messenger.etl.fetchers import btc_flow as btc_flow_module


@pytest.fixture
def load_run_fetch(monkeypatch):
    modules_cache = sys.modules
    ai_news_env_keys = [
        "AI_NEWS_DIRECT",
        "AI_NEWS_DIRECT_CONNECTION",
        "AI_NEWS_DISABLE_PROXY",
        "AI_NEWS_ENABLE_NETWORK",
        "AI_NEWS_EXTRA_PROMPT",
        "AI_NEWS_FALLBACK_PROVIDERS",
        "AI_NEWS_MODEL",
        "AI_NEWS_NO_PROXY",
        "AI_NEWS_PROVIDER",
        "AI_NEWS_THINKING",
        "AI_NEWS_TIMEOUT",
        "API_KEYS_PATH",
        "MARKET_INTEL_SKIP_AI_NEWS",
        "ALIYUN_API_KEY",
        "ALIYUN_API_KEYS",
        "ALIYUN_BASE_URL",
        "ALIYUN_DISABLE_PROXY",
        "ALIYUN_DIRECT_CONNECTION",
        "ALIYUN_ENABLE_NETWORK",
        "ALIYUN_EXTRA_PROMPT",
        "ALIYUN_KEY_1",
        "ALIYUN_MODEL",
        "ALIYUN_SEARCH_STRATEGY",
        "ALIYUN_TIMEOUT",
        "BAILIAN_API_KEY",
        "BAILIAN_API_KEYS",
        "BAILIAN_BASE_URL",
        "BAILIAN_DIRECT_CONNECTION",
        "BAILIAN_DISABLE_PROXY",
        "BAILIAN_ENABLE_NETWORK",
        "BAILIAN_EXTRA_PROMPT",
        "BAILIAN_MODEL",
        "BAILIAN_SEARCH_STRATEGY",
        "BAILIAN_TIMEOUT",
        "DASHSCOPE_API_KEY",
        "DASHSCOPE_API_KEYS",
        "DASHSCOPE_BASE_URL",
        "DASHSCOPE_DIRECT_CONNECTION",
        "DASHSCOPE_DISABLE_PROXY",
        "DASHSCOPE_MODEL",
        "DASHSCOPE_SEARCH_STRATEGY",
        "DASHSCOPE_TIMEOUT",
        "GEMINI_API_KEY",
        "GEMINI_API_KEYS",
        "GEMINI_API_KEY_1",
        "GEMINI_API_KEY_2",
        "GEMINI_BACKUP_KEY",
        "GEMINI_DEFAULT_MODEL",
        "GEMINI_DISABLE_PROXY",
        "GEMINI_DIRECT_CONNECTION",
        "GEMINI_ENABLE_NETWORK",
        "GEMINI_EXTRA_PROMPT",
        "GEMINI_GOOGLE_SEARCH",
        "GEMINI_KEY",
        "GEMINI_KEYS",
        "GEMINI_KEY_1",
        "GEMINI_MODEL",
        "GEMINI_TIMEOUT",
        "GEMINI_PRIMARY_KEY",
        "GEMINI_RESERVE_KEY",
        "GLM_API_KEY",
        "GLM_API_KEYS",
        "GLM_DIRECT_CONNECTION",
        "GLM_DISABLE_PROXY",
        "GLM_ENABLE_NETWORK",
        "GLM_EXTRA_PROMPT",
        "GLM_KEY",
        "GLM_KEYS",
        "GLM_KEY_1",
        "GLM_MODEL",
        "GLM_THINKING",
        "GLM_TIMEOUT",
        "GOOGLE_GEMINI_API_KEY",
        "GOOGLE_GEMINI_DIRECT_CONNECTION",
        "GOOGLE_GEMINI_TIMEOUT",
        "QWEN_API_KEY",
        "QWEN_API_KEYS",
        "QWEN_DIRECT_CONNECTION",
        "QWEN_DISABLE_PROXY",
        "QWEN_MODEL",
        "ZAI_API_KEY",
        "ZHIPU_API_KEY",
        "ZHIPU_API_KEYS",
        "ZHIPU_DIRECT_CONNECTION",
        "ZHIPU_DISABLE_PROXY",
        "ZHIPU_ENABLE_NETWORK",
        "ZHIPU_MODEL",
        "ZHIPU_TIMEOUT",
        "ZHIPUAI_API_KEY",
        "ZHIPUAI_DIRECT_CONNECTION",
        "ZHIPUAI_DISABLE_PROXY",
        "ZHIPUAI_KEYS",
        "ZHIPUAI_MODEL",
        "ZHIPUAI_TIMEOUT",
    ]
    for idx in range(1, 11):
        ai_news_env_keys.extend(
            [
                f"ALIYUN_API_KEY_{idx}",
                f"BAILIAN_API_KEY_{idx}",
                f"DASHSCOPE_API_KEY_{idx}",
                f"GEMINI_API_KEY_{idx}",
                f"GEMINI_KEY_{idx}",
                f"GLM_API_KEY_{idx}",
                f"GLM_KEY_{idx}",
                f"QWEN_API_KEY_{idx}",
                f"ZHIPU_API_KEY_{idx}",
                f"ZHIPUAI_API_KEY_{idx}",
            ]
        )
    for key in ai_news_env_keys:
        monkeypatch.delenv(key, raising=False)

    def _loader(api_keys):
        if api_keys is None:
            monkeypatch.delenv("API_KEYS", raising=False)
            # Keep resolver tests hermetic: a developer's ~/.config file must
            # not override the provider selected by the test environment.
            monkeypatch.setenv(
                "API_KEYS_PATH", "/tmp/market-intel-test-api-keys-does-not-exist.json"
            )
        else:
            monkeypatch.setenv("API_KEYS", json.dumps(api_keys))
        module_name = "daily_messenger.etl.run_fetch"
        if module_name in modules_cache:
            module = importlib.reload(modules_cache[module_name])
        else:
            module = importlib.import_module(module_name)
        return module

    return _loader


def test_fetch_news_events_can_skip_ai_market_news(monkeypatch, load_run_fetch):
    module = load_run_fetch({"ai_news": {"provider": "glm", "keys": ["test-key"]}})
    monkeypatch.setenv("MARKET_INTEL_SKIP_AI_NEWS", "1")
    monkeypatch.setattr(module, "_fetch_ai_rss_events", lambda feeds: ([], []))
    monkeypatch.setattr(
        module,
        "_fetch_arxiv_events",
        lambda params, throttle: ([], module.FetchStatus("arxiv", True, "ok")),
    )

    def fail_ai_news(*args, **kwargs):
        raise AssertionError("AI market news should be skipped")

    monkeypatch.setattr(module, "_fetch_ai_market_news", fail_ai_news)
    statuses = []

    events, ai_updates = module._fetch_news_events(
        {},
        [],
        {},
        0,
        module.setup_logger("test"),
        statuses,
    )

    assert events == []
    assert ai_updates == []
    assert any(status.name == "ai_news" and status.ok for status in statuses)


class DummyResponse:
    def __init__(self, content: str, status_code: int = 200):
        self.content = content.encode("utf-8")
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise Exception(f"status {self.status_code}")


def test_fetch_ai_rss_events_parses_items(monkeypatch, load_run_fetch):
    module = load_run_fetch(
        {
            "ai_feeds": [
                "https://example.com/rss",  # success
                "https://example.com/fail",  # failure
            ]
        }
    )

    rss_payload = """
        <rss><channel>
            <item>
                <title>OpenAI Update</title>
                <pubDate>Mon, 01 Apr 2024 10:00:00 GMT</pubDate>
                <link>https://example.com/rss</link>
            </item>
            <item>
                <title>Another Story</title>
                <pubDate>Tue, 02 Apr 2024 12:00:00 GMT</pubDate>
                <link>https://example.com/rss-2</link>
            </item>
        </channel></rss>
    """

    def fake_get(url, headers=None, timeout=None):
        if "fail" in url:
            raise requests.RequestException("boom")
        return DummyResponse(rss_payload)

    monkeypatch.setattr(requests, "get", fake_get)

    events, statuses = module._fetch_ai_rss_events(module.AI_NEWS_FEEDS)
    assert len(events) == 2
    assert events[0]["source"] == "https://example.com/rss"
    assert events[0]["url"] == "https://example.com/rss"
    assert any(not status.ok for status in statuses)
    assert any(status.ok for status in statuses)


def test_fetch_arxiv_events_parses_entries(monkeypatch, load_run_fetch):
    module = load_run_fetch({})

    feed_payload = """
        <feed xmlns="http://www.w3.org/2005/Atom">
            <entry>
                <title>Sample Paper</title>
                <id>https://arxiv.org/abs/2404.00001</id>
                <updated>2024-04-01T08:00:00Z</updated>
            </entry>
        </feed>
    """

    def fake_get(url, params=None, headers=None, timeout=None):
        assert params["search_query"] == module.ARXIV_QUERY_PARAMS["search_query"]
        return DummyResponse(feed_payload)

    monkeypatch.setattr(requests, "get", fake_get)

    events, status = module._fetch_arxiv_events(module.ARXIV_QUERY_PARAMS, 0)
    assert status.ok
    assert events[0]["title"].startswith("arXiv: Sample Paper")
    assert events[0]["date"] == "2024-04-01"
    assert events[0]["url"] == "https://arxiv.org/abs/2404.00001"


def test_run_includes_ai_sources(tmp_path, monkeypatch, load_run_fetch):
    module = load_run_fetch(
        {
            "ai_feeds": ["https://example.com/rss"],
            "arxiv": {
                "search_query": "cat:cs.AI",
                "max_results": 1,
                "sort_by": "submittedDate",
                "sort_order": "descending",
                "throttle_seconds": 0,
            },
        }
    )

    out_dir = tmp_path / "out"
    monkeypatch.setattr(module, "OUT_DIR", out_dir)

    monkeypatch.setattr(
        module,
        "_fetch_market_snapshot_real",
        lambda api_keys: ({}, module.FetchStatus(name="market", ok=True, message="ok")),
    )
    monkeypatch.setattr(
        module,
        "_simulate_market_snapshot",
        lambda trading_day: (
            {},
            module.FetchStatus(name="market_sim", ok=True, message="ok"),
        ),
    )
    # BTC 叶子函数与模拟器已搬入 fetchers/btc_flow.py，桩必须打在真实来源模块上。
    monkeypatch.setattr(
        btc_flow_module,
        "_fetch_coinbase_spot",
        lambda: (
            50000.0,
            module.FetchStatus(name="coinbase_spot", ok=True, message="ok"),
        ),
    )
    monkeypatch.setattr(
        btc_flow_module,
        "_fetch_okx_funding",
        lambda: (0.001, module.FetchStatus(name="okx_funding", ok=True, message="ok")),
    )
    monkeypatch.setattr(
        btc_flow_module,
        "_fetch_okx_basis",
        lambda spot_price: (
            0.0,
            module.FetchStatus(name="okx_basis", ok=True, message="ok"),
        ),
    )
    monkeypatch.setattr(
        btc_flow_module,
        "_fetch_btc_etf_flow",
        lambda api_keys: (
            12.5,
            module.FetchStatus(name="btc_etf_flow", ok=True, message="ok"),
        ),
    )
    monkeypatch.setattr(
        btc_flow_module,
        "_simulate_btc_theme",
        lambda trading_day: (
            {},
            module.FetchStatus(name="btc_sim", ok=True, message="ok"),
        ),
    )
    monkeypatch.setattr(
        module,
        "_fetch_events_real",
        lambda trading_day, api_keys: (
            [
                {
                    "title": "宏观事件",
                    "date": "2024-04-01",
                    "impact": "high",
                }
            ],
            module.FetchStatus(name="events", ok=True, message="ok"),
        ),
    )
    monkeypatch.setattr(
        module,
        "_fetch_finnhub_earnings",
        lambda trading_day, api_keys: (
            [],
            module.FetchStatus(name="finnhub_earnings", ok=True, message="ok"),
        ),
    )
    monkeypatch.setattr(
        module,
        "_fetch_theme_metrics_from_fmp",
        lambda api_keys: (
            {},
            module.FetchStatus(name="fmp_theme", ok=True, message="fixture"),
        ),
    )
    monkeypatch.setattr(
        module,
        "_edgar_healthcheck",
        lambda: module.FetchStatus(name="edgar", ok=True, message="fixture"),
    )
    monkeypatch.setattr(
        module,
        "_fetch_sentiment_payload",
        lambda previous, statuses: ({}, True),
    )
    monkeypatch.setattr(
        module,
        "_fetch_ai_market_news",
        lambda now_utc, api_keys, logger: (
            [],
            [module.FetchStatus(name="ai_news", ok=True, message="fixture")],
        ),
    )
    monkeypatch.setattr(
        module,
        "_fetch_ai_rss_events",
        lambda feeds: (
            [
                {
                    "title": "RSS Event",
                    "date": "2024-04-02",
                    "impact": "medium",
                    "source": feeds[0],
                    "url": "https://example.com/rss-item",
                }
            ],
            [module.FetchStatus(name="ai_rss_1", ok=True, message="ok")],
        ),
    )
    monkeypatch.setattr(
        module,
        "_fetch_arxiv_events",
        lambda params, throttle: (
            [
                {
                    "title": "arXiv: Paper",
                    "date": "2024-04-03",
                    "impact": "low",
                    "source": "arxiv",
                    "url": "https://arxiv.org/abs/test",
                }
            ],
            module.FetchStatus(name="arxiv", ok=True, message="ok"),
        ),
    )

    result = module.run([])
    assert result == 0

    raw_events_path = out_dir / "raw_events.json"
    assert raw_events_path.exists()
    payload = json.loads(raw_events_path.read_text(encoding="utf-8"))
    titles = {event["title"] for event in payload["events"]}
    assert "宏观事件" in titles
    assert "RSS Event" in titles
    assert "arXiv: Paper" in titles
    assert payload["ai_updates"][0]["title"] == "RSS Event"
    assert payload["ai_updates"][0]["sourceChain"] == [
        {
            "source": "https://example.com/rss",
            "url": "https://example.com/rss-item",
            "title": "RSS Event",
        }
    ]
    assert not any(field in payload["ai_updates"][0] for field in ("summary", "raw_text", "items"))
    arxiv_event = next(event for event in payload["events"] if event["title"] == "arXiv: Paper")
    assert arxiv_event["sourceChain"] == [
        {"source": "arxiv", "url": "https://arxiv.org/abs/test", "title": "arXiv: Paper"}
    ]


def test_raw_event_normalization_strips_unauthorized_news_body(load_run_fetch):
    module = load_run_fetch({})

    _, ai_updates = module._normalize_raw_events_payload(
        [],
        [
            {
                "title": "美股 2026-07-02 交易日资讯",
                "date": "2026-07-02",
                "market": "us",
                "summary": "- 不应落盘的摘要",
                "raw_text": "<news>不应落盘</news>",
                "items": [
                    {
                        "title": "Company filing",
                        "source": "SEC",
                        "url": "https://www.sec.gov/example",
                        "summary": "不应落盘的正文",
                    }
                ],
                "provider": "glm",
            }
        ],
    )

    assert ai_updates == [
        {
            "title": "美股 2026-07-02 交易日资讯",
            "date": "2026-07-02",
            "market": "us",
            "source": "SEC",
            "url": "https://www.sec.gov/example",
            "sourceChain": [
                {
                    "source": "SEC",
                    "url": "https://www.sec.gov/example",
                    "title": "Company filing",
                },
                {"source": "glm", "url": "", "title": "美股 2026-07-02 交易日资讯"},
            ],
        }
    ]
    assert not any(field in ai_updates[0] for field in ("summary", "raw_text", "items"))


def test_fetch_ai_market_news_generates_updates_glm(monkeypatch, load_run_fetch):
    module = load_run_fetch(
        {
            "ai_news": {
                "provider": "glm",
                "model": "glm-4.6",
                "keys": ["PRIMARY_TOKEN"],
                "enable_network": False,
            }
        }
    )
    module.THROTTLE_DISABLED = True

    def fake_call(model, api_key, prompt, enable_network, timeout, thinking, direct_connection):
        assert model == "glm-4.6"
        assert api_key == "PRIMARY_TOKEN"
        assert thinking == "enabled"
        assert direct_connection is True
        assert "<news>" in prompt
        payload = {
            "items": [
                {
                    "category": "sector",
                    "title": "日本韩国美股A股市场资讯",
                    "summary": "日经、KOSPI、A股和美股均出现可验证市场动态。",
                    "source": "市场媒体",
                    "url": "https://news.test/market",
                    "published_at": "2024-04-01",
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

    # _call_glm_chat_completions 已随 AI news fetch 逻辑常驻 ai_news 子模块，
    # 桩必须打在真实来源模块上，否则 ai_news_parse 内部经 ai_news 命名空间解析
    # 到的仍是真实函数。
    monkeypatch.setattr(module.ai_news, "_call_glm_chat_completions", fake_call)

    now = datetime(2024, 4, 2, 10, 0, tzinfo=UTC)
    updates, statuses = module._fetch_ai_market_news(
        now,
        {
            "ai_news": {
                "provider": "glm",
                "model": "glm-4.6",
                "keys": ["PRIMARY_TOKEN"],
                "enable_network": False,
            }
        },
        logger=None,
    )

    assert len(updates) == len(module.AI_NEWS_MARKET_SPECS)
    assert all(update["source"] == "glm" for update in updates)
    assert all(update["summary"] for update in updates)
    assert all(status.ok for status in statuses)


def test_fetch_ai_market_news_rotates_keys_gemini(monkeypatch, load_run_fetch):
    module = load_run_fetch(
        {
            "ai_news": {
                "provider": "gemini",
                "model": "gemini-test",
                "keys": ["PRIMARY_TOKEN", "BACKUP_TOKEN"],
                "enable_network": False,
            }
        }
    )
    module.THROTTLE_DISABLED = True

    call_counter = {"PRIMARY_TOKEN": 0, "BACKUP_TOKEN": 0}

    def fake_call(model, api_key, prompt, enable_network, timeout, direct_connection):
        assert direct_connection is False
        call_counter[api_key] += 1
        if api_key == "PRIMARY_TOKEN":
            raise requests.HTTPError("quota exceeded")
        payload = {
            "items": [
                {
                    "category": "sector",
                    "title": "日本韩国美股A股市场资讯",
                    "summary": "日经、KOSPI、A股和美股均出现可验证市场动态。",
                    "source": "市场媒体",
                    "url": "https://news.test/market",
                    "published_at": "2024-04-02",
                }
            ]
        }
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": f"<news>{json.dumps(payload, ensure_ascii=False)}</news>",
                            }
                        ]
                    }
                }
            ]
        }

    # _call_gemini_generate_content 已随 AI news fetch 逻辑常驻 ai_news 子模块，
    # 桩必须打在真实来源模块上（见上方 GLM 测试说明）。
    monkeypatch.setattr(module.ai_news, "_call_gemini_generate_content", fake_call)

    now = datetime(2024, 4, 3, 12, 0, tzinfo=UTC)
    updates, statuses = module._fetch_ai_market_news(
        now,
        {
            "ai_news": {
                "provider": "gemini",
                "model": "gemini-test",
                "keys": ["PRIMARY_TOKEN", "BACKUP_TOKEN"],
                "enable_network": False,
            }
        },
        logger=None,
    )

    assert len(updates) == len(module.AI_NEWS_MARKET_SPECS)
    assert call_counter["PRIMARY_TOKEN"] >= 1
    assert call_counter["BACKUP_TOKEN"] >= len(module.AI_NEWS_MARKET_SPECS)
    assert all(status.ok for status in statuses)


def test_resolve_edgar_user_agent_raises_on_blank(monkeypatch, load_run_fetch):
    module = load_run_fetch({})
    monkeypatch.setenv("EDGAR_USER_AGENT", "   ")

    with pytest.raises(RuntimeError):
        module._resolve_edgar_user_agent()


def test_resolve_ai_news_settings_env_fallback_gemini(monkeypatch, load_run_fetch):
    monkeypatch.delenv("API_KEYS", raising=False)
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-pro")
    monkeypatch.setenv("GEMINI_ENABLE_NETWORK", "true")
    monkeypatch.setenv("GEMINI_KEY_1", "ENV_KEY_A")
    monkeypatch.setenv("GEMINI_API_KEY_2", "ENV_KEY_B")

    module = load_run_fetch(None)
    settings = module._resolve_ai_news_settings(module.API_KEYS_CACHE)

    assert settings is not None
    assert settings.provider == "gemini"
    assert settings.model == "gemini-2.5-pro"
    assert settings.enable_network is True
    assert settings.direct_connection is False
    tokens = {token for _, token in settings.keys}
    assert {"ENV_KEY_A", "ENV_KEY_B"} <= tokens


def test_resolve_ai_news_settings_defaults_to_glm(monkeypatch, load_run_fetch):
    monkeypatch.delenv("API_KEYS", raising=False)
    monkeypatch.setenv("GLM_KEY_1", "GLM_KEY_PRIMARY")
    monkeypatch.setenv("GLM_ENABLE_NETWORK", "0")

    module = load_run_fetch(None)
    settings = module._resolve_ai_news_settings(module.API_KEYS_CACHE)

    assert settings is not None
    assert settings.provider == "glm"
    assert settings.model == "glm-4.6"
    assert settings.enable_network is False
    assert settings.direct_connection is True
    assert settings.thinking == "enabled"
    tokens = {token for _, token in settings.keys}
    assert "GLM_KEY_PRIMARY" in tokens
