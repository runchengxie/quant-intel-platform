"""覆盖率测试：提升 run_fetch 的分支覆盖率，以便解除 coverage.omit。

聚焦纯函数与中层编排器，叶子抓取函数一律 monkeypatch，避免真实网络请求。
端到端 run() 用 tmp_path 接管 OUT_DIR / STATE_DIR，并对所有外部抓取入口打桩。
"""

import importlib
import json
import sys
from types import SimpleNamespace

import pytest

from daily_messenger.etl.fetchers import btc_flow as btc_flow_module
from daily_messenger.etl.types import FetchStatus


@pytest.fixture
def module():
    name = "daily_messenger.etl.run_fetch"
    if name in sys.modules:
        return importlib.reload(sys.modules[name])
    return importlib.import_module(name)


def _stub(module, monkeypatch, **name_to_value):
    """将军桩收敛为一行：``_stub(m, mp, _foo=(1, FetchStatus(...)))``。

    每个值是一个 ``(return_value, FetchStatus)`` 二元组，生成忽略调用参数的
    ``lambda *a, **k: (return_value, status)`` 注入到 module 命名空间。
    注意必须用 ``*a, **k`` 吞掉调用方传入的参数，否则像
    ``_fetch_btc_etf_flow(api_keys)`` 这样的实参会覆盖桩的默认返回值。
    已是 callable 的值（如 ``boom``）直接注入，不包 lambda。
    """
    for name, value in name_to_value.items():
        if callable(value):
            monkeypatch.setattr(module, name, value)
        else:
            ret, status = value
            # ret/status 放在 *a 之后成为 keyword-only 默认参数，
            # 调用方传入的位置参数（如 api_keys）会被 *a 吞掉，不会覆盖它们。
            monkeypatch.setattr(
                module,
                name,
                lambda *a, ret=ret, status=status, **k: (ret, status),
            )


def _stub_attr(module, monkeypatch, attr, **name_to_value):
    """对 ``module.<attr>`` 子模块批量打桩（如 cboe_putcall.fetch）。"""
    target = getattr(module, attr)
    for name, value in name_to_value.items():
        ret, status = value
        monkeypatch.setattr(
            target,
            name,
            lambda *a, ret=ret, status=status, **k: (ret, status),
        )


def _etl_paths(mod, tmp_path):
    return mod._EtlPaths(
        raw_market=tmp_path / "raw_market.json",
        raw_events=tmp_path / "raw_events.json",
        status=tmp_path / "etl_status.json",
        marker=tmp_path / "fetch_2026-07-27",
    )


# ── 纯函数：状态加载与缓存判断 ───────────────────────────────────────────────


def test_load_previous_market_state_missing_file(module, tmp_path):
    prev_sent, prev_btc = module._load_previous_market_state(tmp_path / "nope.json")
    assert prev_sent == {} and prev_btc == {}


def test_load_previous_market_state_corrupt_json(module, tmp_path):
    p = tmp_path / "raw_market.json"
    p.write_text("{not valid json", encoding="utf-8")
    prev_sent, prev_btc = module._load_previous_market_state(p)
    assert prev_sent == {} and prev_btc == {}


def test_load_previous_market_state_valid(module, tmp_path):
    payload = {
        "sentiment": {"put_call": {"x": 1}},
        "btc": {"etf_net_inflow_musd": 12.5},
    }
    p = tmp_path / "raw_market.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    prev_sent, prev_btc = module._load_previous_market_state(p)
    assert prev_sent == {"put_call": {"x": 1}}
    assert prev_btc == {"etf_net_inflow_musd": 12.5}


def test_status_cache_matches_wrong_date(module, tmp_path):
    p = tmp_path / "etl_status.json"
    p.write_text(json.dumps({"date": "2026-01-01"}), encoding="utf-8")
    assert module._status_cache_matches(p, "2026-07-27") is False


def test_status_cache_matches_corrupt(module, tmp_path):
    p = tmp_path / "etl_status.json"
    p.write_text("oops", encoding="utf-8")
    assert module._status_cache_matches(p, "2026-07-27") is False


def test_status_cache_matches_ok(module, tmp_path):
    p = tmp_path / "etl_status.json"
    p.write_text(json.dumps({"date": "2026-07-27"}), encoding="utf-8")
    assert module._status_cache_matches(p, "2026-07-27") is True


def test_should_skip_cached_force(module, tmp_path):
    paths = _etl_paths(module, tmp_path)
    assert module._should_skip_cached(paths, "2026-07-27", force=True) is False


def test_should_skip_cached_no_marker(module, tmp_path):
    paths = _etl_paths(module, tmp_path)
    # marker 不存在 -> 不跳过
    assert module._should_skip_cached(paths, "2026-07-27", force=False) is False


def test_should_skip_cached_missing_outputs(module, tmp_path):
    paths = _etl_paths(module, tmp_path)
    paths.marker.write_text("", encoding="utf-8")  # marker 存在但输出缺失
    assert module._should_skip_cached(paths, "2026-07-27", force=False) is False


def test_should_skip_cached_match(module, tmp_path):
    paths = _etl_paths(module, tmp_path)
    paths.marker.write_text("", encoding="utf-8")
    paths.raw_market.write_text("{}", encoding="utf-8")
    paths.raw_events.write_text("{}", encoding="utf-8")
    paths.status.write_text(json.dumps({"date": "2026-07-27"}), encoding="utf-8")
    assert module._should_skip_cached(paths, "2026-07-27", force=False) is True


# ── 纯函数：情绪合并与主题性能 ───────────────────────────────────────────────


def test_merge_sentiment_source_ok(module):
    data: dict = {}
    statuses: list = []
    ok = module._merge_sentiment_source(
        data,
        {"a": 1},
        FetchStatus(name="x", ok=True, message="ok"),
        {},
        "fb_key",
        "fb_status",
        "使用上一期",
        statuses,
    )
    assert ok is True
    assert data == {"a": 1}
    assert len(statuses) == 1


def test_merge_sentiment_source_fallback(module):
    data: dict = {}
    statuses: list = []
    ok = module._merge_sentiment_source(
        data,
        None,
        FetchStatus(name="x", ok=False, message="bad"),
        {"fb_key": {"old": 9}},
        "fb_key",
        "fb_status",
        "使用上一期",
        statuses,
    )
    assert ok is False
    assert data == {"fb_key": {"old": 9}}
    # 失败状态 + fallback 状态 两条
    assert len(statuses) == 2


def test_merge_sentiment_source_no_fallback(module):
    data: dict = {}
    statuses: list = []
    ok = module._merge_sentiment_source(
        data,
        None,
        FetchStatus(name="x", ok=False, message="bad"),
        {},
        "fb_key",
        "fb_status",
        "使用上一期",
        statuses,
    )
    assert ok is False
    assert data == {}


def test_theme_performance_from_market_ai_present(module):
    market = {
        "sectors": [
            {"name": "AI", "performance": 1.05},
            {"name": "Defensive", "performance": 0.9},
        ]
    }
    themes = module._theme_performance_from_market(market)
    assert themes == {"ai": {"performance": 1.05}}


def test_theme_performance_from_market_no_ai(module):
    market = {"sectors": [{"name": "Defensive", "performance": 0.9}]}
    assert module._theme_performance_from_market(market) == {}


# ── 中层编排器：行情 / 情绪 / BTC ─────────────────────────────────────────────


def test_fetch_base_market_data_ok(module, monkeypatch):
    fake_market = {"date": "2026-07-27", "indices": []}
    monkeypatch.setattr(
        module,
        "_fetch_market_snapshot_real",
        lambda api_keys: (fake_market, FetchStatus(name="market", ok=True, message="ok")),
    )
    data, ok = module._fetch_base_market_data({}, "2026-07-27", [])
    assert ok is True and data == fake_market


def test_fetch_base_market_data_fallback(module, monkeypatch):
    monkeypatch.setattr(
        module,
        "_fetch_market_snapshot_real",
        lambda api_keys: (None, FetchStatus(name="market", ok=False, message="fail")),
    )
    sim = {"date": "2026-07-27", "indices": [], "simulated": True}
    sim_status = FetchStatus(name="market", ok=True, message="sim")
    monkeypatch.setattr(module, "_simulate_market_snapshot", lambda d: (sim, sim_status))
    data, ok = module._fetch_base_market_data({}, "2026-07-27", [])
    assert ok is False and data["simulated"] is True


def test_fetch_sentiment_payload_ok(module, monkeypatch):
    # _merge_sentiment_source / _fetch_sentiment_payload 已搬入
    # fetchers/aaii_sentiment.py；打桩必须指向真实来源模块，否则 wrapper 内部
    # 调用的真实函数不会被替换。
    monkeypatch.setattr(
        module.aaii_sentiment,
        "_merge_sentiment_source",
        lambda *a, **k: True,
    )
    # 直接验证聚合逻辑：两个源都 ok
    monkeypatch.setattr(
        module.cboe_putcall,
        "fetch",
        lambda: ({}, FetchStatus(name="cboe", ok=True, message="ok")),
    )
    _data, ok = module._fetch_sentiment_payload({}, [])
    assert ok is True


def test_fetch_btc_payload_success(module, monkeypatch):
    ok_status = FetchStatus(name="ok", ok=True, message="ok")
    # 叶子函数已搬入 fetchers/btc_flow.py，桩必须打在真实来源模块上。
    _stub(
        btc_flow_module,
        monkeypatch,
        _fetch_coinbase_spot=(60000.0, ok_status),
        _fetch_okx_funding=(0.0001, ok_status),
        _fetch_okx_basis=(0.001, ok_status),
        _fetch_btc_etf_flow=(50.0, ok_status),
    )
    data, ok = module._fetch_btc_payload({}, "2026-07-27", {}, [])
    assert ok is True
    assert data["spot_price_usd"] == 60000.0
    assert data["etf_net_inflow_musd"] == 50.0


def test_fetch_btc_payload_spot_none_falls_to_sim(module, monkeypatch):
    ok_status = FetchStatus(name="ok", ok=True, message="ok")
    sim_status = FetchStatus(name="btc", ok=True, message="sim")
    sim = {"date": "2026-07-27", "simulated": True}
    _stub(
        btc_flow_module,
        monkeypatch,
        _fetch_coinbase_spot=(None, FetchStatus(name="spot", ok=False, message="no")),
        _fetch_okx_funding=(0.0001, ok_status),
        _fetch_btc_etf_flow=(50.0, ok_status),
        _simulate_btc_theme=(sim, sim_status),
    )
    data, ok = module._fetch_btc_payload({}, "2026-07-27", {}, [])
    assert ok is False
    assert data["simulated"] is True


def test_fetch_btc_payload_flow_fallback(module, monkeypatch):
    ok_status = FetchStatus(name="ok", ok=True, message="ok")
    _stub(
        btc_flow_module,
        monkeypatch,
        _fetch_coinbase_spot=(60000.0, ok_status),
        _fetch_okx_funding=(0.0001, ok_status),
        _fetch_okx_basis=(0.001, ok_status),
        _fetch_btc_etf_flow=(None, FetchStatus(name="flow", ok=False, message="no")),
    )
    data, ok = module._fetch_btc_payload({}, "2026-07-27", {"etf_net_inflow_musd": 33.0}, [])
    # flow 失败但有上一期 -> 用上一期，整体仍 ok=False（因 flow_status.ok=False）
    assert ok is False
    assert data["etf_net_inflow_musd"] == 33.0


# ── 端到端 run()：所有叶子抓取打桩 ───────────────────────────────────────────


def test_run_end_to_end_writes_outputs(module, monkeypatch, tmp_path):
    monkeypatch.setenv("DM_OVERRIDE_DATE", "2026-07-27")
    monkeypatch.setenv("API_KEYS", json.dumps({}))
    monkeypatch.setattr(module, "OUT_DIR", tmp_path / "out")
    monkeypatch.setattr(module, "STATE_DIR", tmp_path / "state")

    # 行情
    fake_market = {
        "date": "2026-07-27",
        "indices": [{"symbol": "SPX", "close": 1.0, "change_pct": 0.1}],
        "sectors": [],
    }
    monkeypatch.setattr(
        module,
        "_fetch_market_snapshot_real",
        lambda api_keys: (fake_market, FetchStatus(name="market", ok=True, message="ok")),
    )
    ok_status = FetchStatus(name="ok", ok=True, message="ok")
    fail_status = FetchStatus(name="no", ok=False, message="no")
    _stub(
        module,
        monkeypatch,
        _fetch_hk_market_snapshot=([], fail_status),
        _fetch_theme_metrics_from_fmp=({}, fail_status),
        _edgar_healthcheck=lambda: ok_status,
        _fetch_events_real=([], fail_status),
        _fetch_finnhub_earnings=([], fail_status),
        _fetch_ai_rss_events=([], [ok_status]),
        _fetch_arxiv_events=([], ok_status),
    )
    # BTC 叶子函数已搬入 fetchers/btc_flow.py，桩必须打在真实来源模块上。
    _stub(
        btc_flow_module,
        monkeypatch,
        _fetch_coinbase_spot=(60000.0, ok_status),
        _fetch_okx_funding=(0.0001, ok_status),
        _fetch_okx_basis=(0.001, ok_status),
        _fetch_btc_etf_flow=(50.0, ok_status),
    )
    _stub_attr(module, monkeypatch, "cboe_putcall", fetch=({}, ok_status))
    _stub_attr(module, monkeypatch, "aaii_sentiment", fetch=({}, ok_status))
    monkeypatch.setattr(
        module,
        "_fetch_ai_market_news",
        lambda now, keys, logger: ([], [FetchStatus(name="ai_news", ok=True, message="ok")]),
    )

    rc = module.run([])
    assert rc == 0
    assert (tmp_path / "out" / "raw_market.json").exists()
    assert (tmp_path / "out" / "raw_events.json").exists()
    assert (tmp_path / "out" / "etl_status.json").exists()
    status = json.loads((tmp_path / "out" / "etl_status.json").read_text(encoding="utf-8"))
    assert status["date"] == "2026-07-27"


# ── 真实行情快照与行情解析（不 stub _fetch_market_snapshot_real 本体） ──────────


def _fake_snapshot(day, close, change_pct, source):
    return SimpleNamespace(day=day, close=close, change_pct=change_pct, source=source)


def test_resolve_index_quote_success(module, monkeypatch):
    monkeypatch.setattr(
        module,
        "_fetch_quote_from_stooq",
        lambda symbol: _fake_snapshot("2026-07-27", 100.0, 1.0, "stooq"),
    )
    snap = module._resolve_index_quote("SPY", {})
    assert snap.close == 100.0
    assert snap.source == "stooq"


def test_resolve_index_quote_all_fail(module, monkeypatch):
    def boom(symbol):
        raise RuntimeError("no source")

    monkeypatch.setattr(module, "_fetch_quote_from_stooq", boom)
    with pytest.raises(RuntimeError):
        module._resolve_index_quote("SPY", {})


def test_resolve_equity_quote_with_yahoo(module, monkeypatch):
    monkeypatch.setattr(
        module,
        "_fetch_quote_from_fmp",
        lambda symbol, key: _fake_snapshot("2026-07-27", 50.0, -0.5, "fmp"),
    )
    monkeypatch.setattr(module, "_yahoo_allowed", lambda: True)
    monkeypatch.setattr(
        module,
        "_fetch_quote_from_yahoo",
        lambda symbol: _fake_snapshot("2026-07-27", 50.0, -0.5, "yahoo"),
    )
    snap = module._resolve_equity_quote("BOTZ", {})
    assert snap.source in {"fmp", "yahoo"}


def test_fetch_market_snapshot_real_success(module, monkeypatch):
    monkeypatch.setattr(
        module,
        "_resolve_index_quote",
        lambda proxy, keys: _fake_snapshot("2026-07-27", 100.0, 1.0, "stooq"),
    )
    monkeypatch.setattr(
        module,
        "_resolve_equity_quote",
        lambda proxy, keys: _fake_snapshot("2026-07-27", 50.0, 2.0, "fmp"),
    )
    market, status = module._fetch_market_snapshot_real({})
    assert status.ok is True
    assert len(market["indices"]) == 2  # SPX + NDX
    assert market["sectors"][0]["name"] == "AI"


def test_fetch_market_snapshot_real_degraded(module, monkeypatch):
    def boom(proxy, keys):
        raise RuntimeError("no index")

    monkeypatch.setattr(module, "_resolve_index_quote", boom)
    monkeypatch.setattr(
        module,
        "_resolve_equity_quote",
        lambda proxy, keys: _fake_snapshot("2026-07-27", 50.0, 2.0, "fmp"),
    )
    market, status = module._fetch_market_snapshot_real({})
    assert status.ok is False
    assert market is None


def test_fetch_events_payload_with_events(module, monkeypatch):
    monkeypatch.setattr(
        module,
        "_fetch_calendar_events",
        lambda d, k, st: [{"title": "Fed", "date": "2026-07-27", "impact": "high", "source": "x"}],
    )
    monkeypatch.setattr(
        module,
        "_fetch_news_events",
        lambda *a, **k: (
            [{"title": "News", "date": "2026-07-27", "impact": "low"}],
            [{"title": "AI", "provider": "glm"}],
        ),
    )
    events, ai = module._fetch_events_payload("2026-07-27", {}, [], {}, 0.0, None, [])
    assert len(events) == 2
    assert ai[0]["source"] == "glm"


def test_fetch_news_events_skips_ai(module, monkeypatch):
    # ai_feeds 为空 -> 不调用 rss
    ok_status = FetchStatus(name="ok", ok=True, message="ok")
    _stub(
        module,
        monkeypatch,
        _fetch_ai_rss_events=([], [ok_status]),
        _fetch_arxiv_events=([], ok_status),
    )
    events, ai = module._fetch_news_events({}, [], {}, 0.0, None, [])
    assert events == [] and ai == []
