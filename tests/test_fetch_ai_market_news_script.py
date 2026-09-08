from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "fetch_ai_market_news.py"
spec = importlib.util.spec_from_file_location("fetch_ai_market_news", SCRIPT)
assert spec and spec.loader
fetch_ai_market_news = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch_ai_market_news)


def test_fetch_news_per_market_keeps_partial_results(monkeypatch) -> None:
    calls: list[str] = []

    def fake_run(command, **_kwargs):
        market = command[command.index("--markets") + 1]
        calls.append(market)
        if market == "cn" and calls.count("cn") == 1:
            raise subprocess.TimeoutExpired(command, timeout=5)
        payload = {
            "provider": "glm",
            "model": "glm-4.6",
            "providers": [{"provider": "glm", "configured": True}],
            "markets_requested": [market],
            "markets": {
                market: {
                    "market": market,
                    "label": market.upper(),
                    **({"news_text": f"{market} ok"} if market == "cn" else {"error": "failed"}),
                }
            },
        }
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(fetch_ai_market_news.subprocess, "run", fake_run)
    monkeypatch.setattr(fetch_ai_market_news.time, "sleep", lambda _seconds: None)

    payload = fetch_ai_market_news.fetch_news_per_market(
        ["cn", "jp"],
        market_timeout=5,
        retries=1,
        sleep_seconds=1,
    )

    assert payload["per_market"] is True
    assert payload["markets"]["cn"]["news_text"] == "cn ok"
    assert len(payload["markets"]["cn"]["attempts"]) == 2
    assert payload["markets"]["cn"]["attempts"][0]["error"] == "timeout after 5s"
    assert payload["markets"]["jp"]["error"] == "failed"
    assert payload["markets"]["jp"]["attempts"][0]["ok"] is False
