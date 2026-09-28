import hashlib
import json

import pytest

from scripts.import_market_daily_report import _normalize, import_report


def _payload():
    return {
        "schema_version": "1.0",
        "as_of": "2026-09-20T01:00:00+00:00",
        "generated_at": "2026-09-20T01:00:00+00:00",
        "run_id": "daily-2026-09-19",
        "facts": [
            {
                "id": "index.spx.change_percent",
                "unit": "percent",
                "value": 0.16,
                "quality": "reviewed",
                "source_url": "https://example.test/report",
                "observation_date": "2026-09-19",
            }
        ],
        "events": [],
        "claims": [
            {
                "claim": "SPX rose",
                "evidence_ids": ["index.spx.change_percent"],
                "sources": ["https://example.test"],
            }
        ],
        "source_status": {"facts": {"quality": "ok"}},
        "quality_summary": {"status": "ok"},
        "content_hash": "ignored-by-fixture",
    }


def _source(tmp_path, payload):
    payload["content_hash"] = None
    payload["content_hash"] = hashlib.sha256(
        json.dumps(_normalize(payload), default=str, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    source = tmp_path / "daily_report.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    manifest = tmp_path / "publication.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "publication": "public",
                "report_file": source.name,
                "report_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "run_id": payload["run_id"],
                "content_hash": payload["content_hash"],
            }
        ),
        encoding="utf-8",
    )
    return source, manifest


def test_import_report_writes_public_json_and_markdown(tmp_path):
    source, manifest = _source(tmp_path, _payload())
    output = tmp_path / "site"
    result = import_report(source, output, manifest)
    assert result == "2026-09-19"
    assert (output / "artifacts/public/data/market_daily_report.json").is_file()
    assert (output / "artifacts/public/data/market_daily_report.json").exists()
    assert "SPX rose" in (output / "artifacts/public/reports/2026-09-19-market-daily.md").read_text()


def test_import_report_writes_reference_free_markdown_with_all_treasury_tenors(tmp_path):
    payload = _payload()
    payload["source_status"] = {"rates": {"quality": "ok", "reason": "ok"}}
    payload["sections"] = [{"key": "movers", "claims": ["index.spx.change_percent"]}]
    treasury_url = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/all/202609?_format=csv&field_tdr_date_value_month=202609&page=&type=daily_treasury_yield_curve"
    for tenor, level, change in (("2y", 4.81, -6), ("5y", 4.98, -5), ("10y", 5.17, -1), ("30y", 5.49, 2)):
        for metric, value, unit in (
            ("level_percent", level, "percent"),
            ("change_bp", change, "basis_points"),
        ):
            payload["facts"].append(
                {
                    "id": f"treasury.{tenor}.{metric}",
                    "metric": "yield_level" if metric == "level_percent" else "yield_change",
                    "value": value,
                    "unit": unit,
                    "quality": "ok",
                    "source_url": treasury_url,
                    "observation_date": "2026-09-19",
                }
            )
    source, manifest = _source(tmp_path, payload)
    output = tmp_path / "site"
    import_report(source, output, manifest)

    original = (output / "artifacts/public/reports/2026-09-19-market-daily.md").read_text()
    reading = (output / "artifacts/public/reports/2026-09-19-market-daily-no-citations.md").read_text()
    assert "[来源1](https://example.test)" in original
    assert "证据：" in original
    assert "| 来源 |" in original
    assert "|---|---:|---:|---|---|" in original
    assert "SPX rose" in reading
    assert "| 5 年期 | 4.98% | -5.00 bp | 2026-09-19 |" in reading
    assert "| 30 年期 | 5.49% | +2.00 bp | 2026-09-19 |" in reading
    assert "|---|---:|---:|---|" in reading
    assert "数据状态：ok" not in reading
    assert "报告生成时间：" not in reading
    assert "## 数据质量与核验说明" not in reading
    assert "https://" not in reading
    assert "证据：" not in reading
    assert "| 来源 |" not in reading
    assert "[来源" not in reading
    assert (
        reading.index("## 美股市场表现")
        < reading.index("## 主要个股")
        < reading.index("## 美债收益率")
        < reading.index("## 布伦特、金银与比特币")
    )
    plain = (output / "artifacts/public/reports/2026-09-19-market-daily.txt").read_text()
    assert (
        plain.index("一、美股市场表现")
        < plain.index("二、重点个股")
        < plain.index("三、美债收益率")
        < plain.index("四、跨资产行情")
    )
    assert plain.index("SPX rose") < plain.index("三、美债收益率")


def test_markdown_keeps_treasury_level_when_daily_change_is_missing(tmp_path):
    payload = _payload()
    payload["facts"].append(
        {
            "id": "treasury.2y.level_percent",
            "metric": "yield_level",
            "value": 4.25,
            "unit": "percent",
            "quality": "ok",
            "source_url": "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/all/202609?_format=csv&field_tdr_date_value_month=202609&page=&type=daily_treasury_yield_curve",
            "observation_date": "2026-09-19",
        }
    )
    source, manifest = _source(tmp_path, payload)
    output = tmp_path / "site"
    import_report(source, output, manifest)
    for suffix in ("", "-no-citations"):
        report = (output / f"artifacts/public/reports/2026-09-19-market-daily{suffix}.md").read_text()
        assert "| 2 年期 | 4.25% | — | 2026-09-19 |" in report


def test_markdown_includes_public_source_status_without_private_metadata(tmp_path):
    payload = _payload()
    payload["source_status"] = {
        "quotes": {"quality": "ok", "reason": "all_indices_fresh"},
        "research": {"quality": "reviewed", "reason": "source_audited"},
    }
    payload["quality_summary"]["reviewed_source_cutoff"] = "2026-09-19T23:59:59-04:00"
    payload["private_review_notes"] = "DO_NOT_PUBLISH"
    source, manifest = _source(tmp_path, payload)
    output = tmp_path / "site"
    import_report(source, output, manifest)
    markdown = (output / "artifacts/public/reports/2026-09-19-market-daily.md").read_text()
    assert "## 数据质量与核验说明" in markdown
    assert "| 指数行情 | 已核实 | 目标交易日数据齐全 |" in markdown
    assert "| 研究材料 | 已审阅 | 来源已逐条核查 |" in markdown
    assert "2026-09-19T23:59:59-04:00" in markdown
    assert "DO_NOT_PUBLISH" not in markdown


def test_reference_free_backfill_keeps_only_short_notice(tmp_path):
    payload = _payload()
    payload["as_of"] = payload["generated_at"] = "2026-09-21T01:00:00+00:00"
    payload["quality_summary"] = {
        "status": "ok",
        "revision": "historical_backfill",
        "reviewed_source_cutoff": "2026-09-19T23:59:59-04:00",
    }
    source, manifest = _source(tmp_path, payload)
    output = tmp_path / "site"
    import_report(source, output, manifest)
    reading = (output / "artifacts/public/reports/2026-09-19-market-daily-no-citations.md").read_text()
    assert "事后整理" in reading
    assert "历史补报：" not in reading
    assert "新闻资料截止：" not in reading
    assert "2026-09-21T01:00:00+00:00" not in reading
    assert "2026-09-19T23:59:59-04:00" not in reading


def test_equity_pairs_appear_in_public_json_and_both_markdown_editions(tmp_path):
    payload = _payload()
    for field, value, metric, unit in (
        ("close", 200.5, "stock_close", "USD/share"),
        ("change_percent", 1.25, "daily_return", "percent"),
    ):
        payload["facts"].append(
            {
                "id": f"equity.msft.{field}",
                "instrument": "MSFT",
                "value": value,
                "metric": metric,
                "unit": unit,
                "source": "Yahoo Finance",
                "quality": "ok",
                "source_url": "https://finance.yahoo.com/quote/MSFT/history/",
                "observation_date": "2026-09-19",
            }
        )
    source, manifest = _source(tmp_path, payload)
    output = tmp_path / "site"
    import_report(source, output, manifest)
    public = json.loads((output / "artifacts/public/data/market_daily_report.json").read_text())
    assert len([row for row in public["facts"] if row["id"].startswith("equity.msft.")]) == 2
    for suffix in ("", "-no-citations"):
        report = (output / f"artifacts/public/reports/2026-09-19-market-daily{suffix}.md").read_text()
        assert "| MSFT | 200.50 美元 | +1.25% | 2026-09-19 |" in report
        assert (
            report.index("## 美股市场表现") < report.index("## 美股个股行情") < report.index("## 美债收益率")
        )


def test_complete_equity_status_requires_six_core_symbols(tmp_path):
    payload = _payload()
    payload["source_status"]["equities"] = {"quality": "ok"}
    source, manifest = _source(tmp_path, payload)
    with pytest.raises(ValueError, match="market date mismatch"):
        import_report(source, tmp_path / "site", manifest)


def test_equity_price_without_matching_return_is_rejected(tmp_path):
    payload = _payload()
    payload["facts"].append(
        {
            "id": "equity.msft.close",
            "instrument": "MSFT",
            "value": 200.5,
            "metric": "stock_close",
            "unit": "USD/share",
            "source": "Yahoo Finance",
            "quality": "ok",
            "source_url": "https://finance.yahoo.com/quote/MSFT/history/",
            "observation_date": "2026-09-19",
        }
    )
    source, manifest = _source(tmp_path, payload)
    with pytest.raises(ValueError, match="market date mismatch"):
        import_report(source, tmp_path / "site", manifest)


@pytest.mark.parametrize(
    "bad_id,bad_value",
    [
        ("equity.msft.foo", 200.5),
        ("equity.msft.close", -200.5),
        ("equity.msft.change_percent", 999),
    ],
)
def test_invalid_equity_ids_or_values_are_rejected(tmp_path, bad_id, bad_value):
    payload = _payload()
    for field, value, metric, unit in (
        ("close", 200.5, "stock_close", "USD/share"),
        ("change_percent", 1.25, "daily_return", "percent"),
    ):
        payload["facts"].append(
            {
                "id": f"equity.msft.{field}",
                "instrument": "MSFT",
                "value": value,
                "metric": metric,
                "unit": unit,
                "source": "Yahoo Finance",
                "quality": "ok",
                "source_url": "https://finance.yahoo.com/quote/MSFT/history/",
                "observation_date": "2026-09-19",
            }
        )
    if bad_id == "equity.msft.foo":
        payload["facts"].append({"id": bad_id, "value": bad_value})
    else:
        next(row for row in payload["facts"] if row["id"] == bad_id)["value"] = bad_value
    source, manifest = _source(tmp_path, payload)
    with pytest.raises(ValueError, match="market date mismatch"):
        import_report(source, tmp_path / "site", manifest)


def test_mover_quote_needs_audited_ticker_evidence(tmp_path):
    payload = _payload()
    for field, value, metric, unit in (
        ("close", 113.94, "stock_close", "USD/share"),
        ("change_percent", 3.2, "daily_return", "percent"),
    ):
        payload["facts"].append(
            {
                "id": f"equity.akam.{field}",
                "instrument": "AKAM",
                "value": value,
                "metric": metric,
                "unit": unit,
                "source": "Yahoo Finance",
                "quality": "ok",
                "source_url": "https://finance.yahoo.com/quote/AKAM/history/",
                "observation_date": "2026-09-19",
            }
        )
    source, manifest = _source(tmp_path, payload)
    with pytest.raises(ValueError, match="market date mismatch"):
        import_report(source, tmp_path / "site", manifest)
    payload["source_status"]["research"] = {"quality": "reviewed"}
    payload["source_status"]["equities"] = {
        "quality": "degraded",
        "reviewed_movers": [
            {"ticker": "AKAM", "evidence_id": "reviewed.12"},
        ],
    }
    payload["sections"] = [{"key": "movers", "claims": ["reviewed.12"]}]
    payload["events"] = [
        {
            "id": "reviewed.12",
            "event_type": "web_gainers_close",
            "quality": "reviewed",
            "source_url": "https://example.test/story",
            "actual": "AKAM rose",
        }
    ]
    payload["claims"].append(
        {
            "claim": "AKAM rose",
            "evidence_ids": ["reviewed.12"],
            "sources": ["https://example.test/story"],
            "status": "accepted",
            "confidence": "confirmed",
            "provider": "source_audit",
        }
    )
    source, manifest = _source(tmp_path, payload)
    import_report(source, tmp_path / "site", manifest)
    payload["events"][0]["event_type"] = "web_company_news_event"
    source, manifest = _source(tmp_path, payload)
    with pytest.raises(ValueError, match="market date mismatch"):
        import_report(source, tmp_path / "site", manifest)


def test_markdown_explains_unavailable_research_without_implying_a_source_exists(tmp_path):
    payload = _payload()
    payload["source_status"] = {"research": {"quality": "degraded", "reason": "not_connected"}}
    source, manifest = _source(tmp_path, payload)
    output = tmp_path / "site"
    import_report(source, output, manifest)
    markdown = (output / "artifacts/public/reports/2026-09-19-market-daily.md").read_text()
    assert "| 研究材料 | 有缺项 | 研究材料尚未接入，不提供未经核实的解释 |" in markdown


def test_import_report_keeps_five_dates_and_backfill_does_not_replace_latest(tmp_path):
    output = tmp_path / "site"
    for day in ("2026-09-18", "2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24", "2026-09-25"):
        work = tmp_path / day
        work.mkdir()
        payload = _payload()
        payload["run_id"] = f"daily-{day}"
        payload["as_of"] = f"{day}T23:00:00-04:00"
        payload["generated_at"] = payload["as_of"]
        payload["facts"] = []
        payload["claims"] = []
        source, manifest = _source(work, payload)
        import_report(source, output, manifest)

    history = json.loads((output / "artifacts/public/data/market_daily_reports.json").read_text())
    assert [row["run_id"] for row in history["reports"]] == [
        "daily-2026-09-25",
        "daily-2026-09-24",
        "daily-2026-09-23",
        "daily-2026-09-22",
        "daily-2026-09-21",
    ]
    assert (
        json.loads((output / "artifacts/public/data/market_daily_report.json").read_text())["run_id"]
        == "daily-2026-09-25"
    )

    work = tmp_path / "revision"
    work.mkdir()
    payload = _payload()
    payload.update(
        run_id="daily-2026-09-24",
        as_of="2026-09-25T15:00:00+00:00",
        generated_at="2026-09-25T15:00:00+00:00",
        quality_summary={"status": "degraded", "revision": "historical_backfill"},
        facts=[],
        claims=[],
    )
    source, manifest = _source(work, payload)
    import_report(source, output, manifest)
    history = json.loads((output / "artifacts/public/data/market_daily_reports.json").read_text())
    assert history["reports"][1]["quality_summary"]["revision"] == "historical_backfill"
    assert (
        json.loads((output / "artifacts/public/data/market_daily_report.json").read_text())["run_id"]
        == "daily-2026-09-25"
    )


def test_import_report_rejects_credentials(tmp_path):
    payload = _payload()
    payload["claims"][0]["claim"] = "API_KEY leaked"
    source, manifest = _source(tmp_path, payload)
    with pytest.raises(ValueError, match="credentials"):
        import_report(source, tmp_path / "site", manifest)


def test_import_report_renders_sourced_macro_facts_for_new_york_date(tmp_path):
    payload = _payload()
    payload.update(
        as_of="2026-09-24T01:00:00+00:00",
        generated_at="2026-09-24T01:00:00+00:00",
        run_id="daily-2026-09-23",
        claims=[],
        facts=[
            {
                "id": "treasury.10y.change_bp",
                "metric": "yield_change",
                "value": -5.0,
                "unit": "basis_points",
                "quality": "ok",
                "source_url": "https://fred.stlouisfed.org/series/DGS10",
                "observation_date": "2026-09-23",
            },
            {
                "id": "macro.cpi_yoy",
                "value": 3.4,
                "unit": "percent_yoy",
                "source_url": "https://fred.stlouisfed.org/series/CPIAUCNS",
                "observation_date": "2026-08-01",
            },
        ],
        quality_summary={"status": "degraded"},
        missing_sources=["quotes", "research", "rates_lag"],
    )
    source, manifest = _source(tmp_path, payload)

    assert import_report(source, tmp_path / "site", manifest) == "2026-09-23"
    markdown = (tmp_path / "site/artifacts/public/reports/2026-09-23-market-daily.md").read_text()
    assert "| 10 年期 | — | -5.00 bp | 2026-09-23 | [FRED]" in markdown
    assert "| CPI 同比 | 3.40% | 2026-08-01 | [FRED]" in markdown
    assert "| 2026-08-01 |" in markdown
    assert "https://fred.stlouisfed.org/series/CPIAUCNS" in markdown
    assert "指数行情" in markdown
    assert "美债收益率当日变动" in markdown


def test_import_report_rejects_fixture_status(tmp_path):
    payload = _payload()
    payload["quality_summary"]["status"] = "fixture"
    source, manifest = _source(tmp_path, payload)

    with pytest.raises(ValueError, match="fixture"):
        import_report(source, tmp_path / "site", manifest)


def test_import_report_renders_official_rates_and_reviewed_indexes(tmp_path):
    payload = _payload()
    payload.update(
        as_of="2026-09-24T08:30:00+00:00",
        generated_at="2026-09-24T08:30:00+00:00",
        run_id="daily-2026-09-23",
        facts=[
            {
                "id": "treasury.10y.change_bp",
                "metric": "yield_change",
                "value": 15.0,
                "unit": "basis_points",
                "quality": "ok",
                "source_url": "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/all/202609?_format=csv&field_tdr_date_value_month=202609&page=&type=daily_treasury_yield_curve",
                "observation_date": "2026-09-23",
            },
            {
                "id": "index.spx.change_percent",
                "unit": "percent",
                "value": -0.8,
                "quality": "reviewed",
                "source_url": "https://abcnews.com/amp/Business/example",
                "observation_date": "2026-09-23",
            },
        ],
        claims=[
            {
                "claim": "经核实的解释",
                "evidence_ids": ["index.spx.change_percent"],
                "sources": ["https://abcnews.com/amp/Business/example"],
            }
        ],
    )
    source, manifest = _source(tmp_path, payload)
    assert import_report(source, tmp_path / "site", manifest) == "2026-09-23"
    markdown = (tmp_path / "site/artifacts/public/reports/2026-09-23-market-daily.md").read_text()
    assert "报告生成时间：2026-09-24T08:30:00+00:00" in markdown
    assert "| 标普 500 | -0.80% | 2026-09-23 | [核实报道]" in markdown
    assert "| 10 年期 | — | +15.00 bp | 2026-09-23 | [美国财政部]" in markdown
    assert "美国财政部" in markdown


@pytest.mark.parametrize("quality", ["rejected", "lagged"])
def test_import_report_rejects_same_day_unapproved_treasury_fact(tmp_path, quality):
    payload = _payload()
    payload["facts"] = [
        {
            "id": "treasury.2y.change_bp",
            "metric": "yield_change",
            "value": 10,
            "unit": "basis_points",
            "quality": quality,
            "source_url": "https://fred.stlouisfed.org/series/DGS2",
            "observation_date": "2026-09-19",
        }
    ]
    payload["claims"] = []
    source, manifest = _source(tmp_path, payload)
    with pytest.raises(ValueError, match="daily report market date mismatch"):
        import_report(source, tmp_path / "site", manifest)


def _cross_asset_payload():
    payload = _payload()
    treasury_url = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/all/202609?_format=csv&field_tdr_date_value_month=202609&page=&type=daily_treasury_yield_curve"
    facts = []
    for tenor, level, change in (("2y", 4.15, 5), ("10y", 4.25, 7)):
        common = {
            "instrument": f"US_TREASURY_{tenor.upper()}",
            "source": "US Treasury",
            "source_url": treasury_url,
            "source_time": "2026-09-25T11:00:00+00:00",
            "retrieved_at": "2026-09-25T11:00:00+00:00",
            "quality": "ok",
            "observation_date": "2026-09-24",
        }
        facts.extend(
            [
                {
                    "id": f"treasury.{tenor}.level_percent",
                    "metric": "yield_level",
                    "value": level,
                    "previous": level - change / 100,
                    "change": None,
                    "unit": "percent",
                    **common,
                },
                {
                    "id": f"treasury.{tenor}.change_bp",
                    "metric": "yield_change",
                    "value": change,
                    "previous": None,
                    "change": change,
                    "unit": "basis_points",
                    **common,
                },
            ]
        )
    for asset, ticker, metric, unit, value in (
        ("brent", "BZX26.NYM", "commodity_close", "USD/barrel", 71.25),
        ("gold", "GCZ26.CMX", "commodity_close", "USD/troy_ounce", 3980.5),
        ("silver", "SIZ26.CMX", "commodity_close", "USD/troy_ounce", 47.12),
        ("bitcoin", "BTC%3DF", "crypto_futures_close", "USD/bitcoin", 108500),
    ):
        url = f"https://finance.yahoo.com/quote/{ticker}/history/"
        common = {
            "instrument": f"{asset} ({ticker})",
            "source": "Yahoo Finance",
            "source_url": url,
            "source_time": "2026-09-25T11:00:00+00:00",
            "retrieved_at": "2026-09-25T11:00:00+00:00",
            "quality": "ok",
            "observation_date": "2026-09-24",
        }
        facts.extend(
            [
                {
                    "id": f"cross_asset.{asset}.close",
                    "metric": metric,
                    "value": value,
                    "previous": None,
                    "change": None,
                    "unit": unit,
                    **common,
                },
                {
                    "id": f"cross_asset.{asset}.change_percent",
                    "metric": "daily_return",
                    "value": 1.2,
                    "previous": None,
                    "change": 1.2,
                    "unit": "percent",
                    **common,
                },
            ]
        )
    payload.update(
        run_id="daily-2026-09-24",
        as_of="2026-09-25T11:00:00+00:00",
        generated_at="2026-09-25T11:00:00+00:00",
        facts=facts,
        claims=[],
        source_status={"rates": {"quality": "ok"}, "cross_asset": {"quality": "ok"}},
        missing_sources=[],
    )
    return payload


def test_import_report_accepts_complete_same_day_yahoo_index_set(tmp_path):
    payload = _cross_asset_payload()
    for key, symbol, value in (
        ("spx", "%5EGSPC", -0.02),
        ("dow", "%5EDJI", -0.31),
        ("nasdaq", "%5EIXIC", 0.01),
        ("russell2000", "%5ERUT", 0.42),
    ):
        payload["facts"].append(
            {
                "id": f"index.{key}.change_percent",
                "metric": "daily_return",
                "instrument": key,
                "value": value,
                "unit": "percent",
                "quality": "ok",
                "source": "Yahoo Finance",
                "source_url": f"https://finance.yahoo.com/quote/{symbol}/history/",
                "observation_date": "2026-09-24",
                "source_time": "2026-09-25T11:00:00+00:00",
                "retrieved_at": "2026-09-25T11:00:00+00:00",
            }
        )
    source, manifest = _source(tmp_path, payload)

    assert import_report(source, tmp_path / "site", manifest) == "2026-09-24"
    markdown = (tmp_path / "site/artifacts/public/reports/2026-09-24-market-daily.md").read_text()
    assert "| 标普 500 | -0.02% | 2026-09-24 | [Yahoo Finance]" in markdown


def test_import_report_rejects_partial_yahoo_index_set(tmp_path):
    payload = _cross_asset_payload()
    payload["facts"].append(
        {
            "id": "index.spx.change_percent",
            "metric": "daily_return",
            "instrument": "S&P 500",
            "value": -0.02,
            "unit": "percent",
            "quality": "ok",
            "source": "Yahoo Finance",
            "source_url": "https://finance.yahoo.com/quote/%5EGSPC/history/",
            "observation_date": "2026-09-24",
            "source_time": "2026-09-25T11:00:00+00:00",
            "retrieved_at": "2026-09-25T11:00:00+00:00",
        }
    )
    source, manifest = _source(tmp_path, payload)

    with pytest.raises(ValueError, match="market date mismatch"):
        import_report(source, tmp_path / "site", manifest)


def test_import_report_publishes_same_day_rates_and_cross_asset_table(tmp_path):
    source, manifest = _source(tmp_path, _cross_asset_payload())

    assert import_report(source, tmp_path / "site", manifest) == "2026-09-24"
    markdown = (tmp_path / "site/artifacts/public/reports/2026-09-24-market-daily.md").read_text()
    public = json.loads((tmp_path / "site/artifacts/public/data/market_daily_report.json").read_text())

    assert "| 2 年期 | 4.15% | +5.00 bp | 2026-09-24 | [美国财政部]" in markdown
    assert "| 布伦特期货 | 71.25 美元/桶 | +1.20% | 2026-09-24 | [Yahoo Finance]" in markdown
    assert "| CME 比特币期货 | 108,500.00 美元/BTC | +1.20% | 2026-09-24 | [Yahoo Finance]" in markdown
    assert len(public["facts"]) == 12
    assert public["source_status"]["cross_asset"]["quality"] == "ok"


def test_import_accepts_dated_futures_and_rejects_wrong_delivery_month(tmp_path):
    payload = _cross_asset_payload()
    expected = {"brent": "BZX26.NYM", "gold": "GCZ26.CMX", "silver": "SIZ26.CMX"}
    for fact in payload["facts"]:
        parts = fact["id"].split(".")
        if len(parts) == 3 and parts[0] == "cross_asset" and parts[1] in expected:
            symbol = expected[parts[1]]
            fact["source_url"] = f"https://finance.yahoo.com/quote/{symbol}/history/"
            fact["instrument"] = f"dated future ({symbol})"
    source, manifest = _source(tmp_path, payload)
    assert import_report(source, tmp_path / "site", manifest) == "2026-09-24"

    for fact in payload["facts"]:
        if fact["id"].startswith("cross_asset.brent."):
            fact["source_url"] = "https://finance.yahoo.com/quote/BZZ26.NYM/history/"
            fact["instrument"] = "dated future (BZZ26.NYM)"
    source, manifest = _source(tmp_path, payload)
    with pytest.raises(ValueError, match="market date mismatch"):
        import_report(source, tmp_path / "site", manifest)


def test_import_report_rejects_continuous_fmp_commodity_pair(tmp_path):
    payload = _cross_asset_payload()
    fmp_url = (
        "https://site.financialmodelingprep.com/developer/docs/stable/commodities-historical-price-eod-full"
    )
    for fact in payload["facts"]:
        if fact["id"].startswith("cross_asset.brent."):
            fact.update(
                source="Financial Modeling Prep",
                source_url=fmp_url,
                instrument="Brent (FMP BZUSD, continuous)",
            )
    source, manifest = _source(tmp_path, payload)

    with pytest.raises(ValueError, match="market date mismatch"):
        import_report(source, tmp_path / "site", manifest)


def test_import_report_rejects_continuous_yahoo_commodity_pair(tmp_path):
    payload = _cross_asset_payload()
    for fact in payload["facts"]:
        if fact["id"].startswith("cross_asset.brent."):
            fact.update(
                source_url="https://finance.yahoo.com/quote/BZ%3DF/history/",
                instrument="Brent continuous future (BZ=F)",
            )
    source, manifest = _source(tmp_path, payload)
    with pytest.raises(ValueError, match="market date mismatch"):
        import_report(source, tmp_path / "site", manifest)


def test_import_report_accepts_separate_fmp_btc_spot_pair(tmp_path):
    payload = _cross_asset_payload()
    base = payload["facts"][-1].copy()
    base.update(
        instrument="BTC/USD cryptocurrency EOD (FMP BTCUSD)",
        source="Financial Modeling Prep",
        source_url="https://site.financialmodelingprep.com/developer/docs/stable/cryptocurrency-historical-price-eod-full",
    )
    payload["facts"].extend(
        [
            {
                **base,
                "id": "cross_asset.bitcoin_spot.close",
                "metric": "crypto_spot_close",
                "value": 84093.13,
                "unit": "USD/bitcoin",
            },
            {
                **base,
                "id": "cross_asset.bitcoin_spot.change_percent",
                "metric": "daily_return",
                "value": -0.35,
                "unit": "percent",
            },
        ]
    )
    source, manifest = _source(tmp_path, payload)

    assert import_report(source, tmp_path / "site", manifest) == "2026-09-24"
    markdown = (tmp_path / "site/artifacts/public/reports/2026-09-24-market-daily.md").read_text()
    assert "| BTC/USD 现货 | 84,093.13 美元/BTC | -0.35% | 2026-09-24 | [FMP]" in markdown
    assert "| CME 比特币期货 |" in markdown


def test_import_report_rejects_spot_fact_mislabeled_as_cme_future(tmp_path):
    payload = _cross_asset_payload()
    base = payload["facts"][-1].copy()
    base.update(
        id="cross_asset.bitcoin_spot.close",
        metric="crypto_spot_close",
        instrument="CME Bitcoin continuous futures (BTC=F)",
        source="Financial Modeling Prep",
        source_url="https://site.financialmodelingprep.com/developer/docs/stable/cryptocurrency-historical-price-eod-full",
        value=84093.13,
        unit="USD/bitcoin",
    )
    payload["facts"].append(base)
    source, manifest = _source(tmp_path, payload)

    with pytest.raises(ValueError, match="market date mismatch"):
        import_report(source, tmp_path / "site", manifest)


@pytest.mark.parametrize(
    ("source_name", "source_url", "instrument", "label"),
    [
        (
            "Data provided by CoinGecko",
            "https://www.coingecko.com/en/api",
            "BTC/USD spot at 16:00 ET (CoinGecko bitcoin/USD)",
            "Data provided by CoinGecko",
        ),
        (
            "Kraken",
            "https://www.kraken.com/prices/bitcoin",
            "BTC/USD spot at 16:00 ET (Kraken XBT/USD)",
            "Kraken",
        ),
    ],
)
def test_import_report_accepts_authorized_btc_spot_fallbacks(
    tmp_path, source_name, source_url, instrument, label
):
    payload = _cross_asset_payload()
    base = payload["facts"][-1].copy()
    base.update(source=source_name, source_url=source_url, instrument=instrument)
    payload["facts"].extend(
        [
            {
                **base,
                "id": "cross_asset.bitcoin_spot.close",
                "metric": "crypto_spot_close",
                "value": 84012.8,
                "unit": "USD/bitcoin",
            },
            {
                **base,
                "id": "cross_asset.bitcoin_spot.change_percent",
                "metric": "daily_return",
                "value": -0.43,
                "unit": "percent",
            },
        ]
    )
    source, manifest = _source(tmp_path, payload)

    assert import_report(source, tmp_path / "site", manifest) == "2026-09-24"
    markdown = (tmp_path / "site/artifacts/public/reports/2026-09-24-market-daily.md").read_text()
    assert f"[{label}]({source_url})" in markdown


def test_import_report_rejects_spot_fallback_with_mismatched_attribution(tmp_path):
    payload = _cross_asset_payload()
    base = payload["facts"][-1].copy()
    base.update(
        source="Kraken",
        source_url="https://www.coingecko.com/en/api",
        instrument="BTC/USD spot at 16:00 ET (Kraken XBT/USD)",
    )
    payload["facts"].extend(
        [
            {
                **base,
                "id": "cross_asset.bitcoin_spot.close",
                "metric": "crypto_spot_close",
                "value": 84012.8,
                "unit": "USD/bitcoin",
            },
            {
                **base,
                "id": "cross_asset.bitcoin_spot.change_percent",
                "metric": "daily_return",
                "value": -0.43,
                "unit": "percent",
            },
        ]
    )
    source, manifest = _source(tmp_path, payload)

    with pytest.raises(ValueError, match="market date mismatch"):
        import_report(source, tmp_path / "site", manifest)


def test_import_report_rejects_fmp_commodity_with_wrong_symbol(tmp_path):
    payload = _cross_asset_payload()
    fmp_url = (
        "https://site.financialmodelingprep.com/developer/docs/stable/commodities-historical-price-eod-full"
    )
    for fact in payload["facts"]:
        if fact["id"].startswith("cross_asset.brent."):
            fact.update(
                source="Financial Modeling Prep",
                source_url=fmp_url,
                instrument="Brent (FMP GCUSD, continuous)",
            )
    source, manifest = _source(tmp_path, payload)

    with pytest.raises(ValueError, match="market date mismatch"):
        import_report(source, tmp_path / "site", manifest)


def test_partial_cross_asset_gap_names_only_unavailable_contract(tmp_path):
    payload = _cross_asset_payload()
    payload["facts"] = [
        fact for fact in payload["facts"] if not fact["id"].startswith("cross_asset.bitcoin.")
    ]
    payload["missing_sources"] = ["cross_asset"]
    payload["source_status"]["cross_asset"] = {"quality": "degraded"}
    source, manifest = _source(tmp_path, payload)

    import_report(source, tmp_path / "site", manifest)
    markdown = (tmp_path / "site/artifacts/public/reports/2026-09-24-market-daily.md").read_text()
    assert "尚缺：比特币期货行情。" in markdown
    assert "尚缺：布伦特、金银或比特币行情。" not in markdown


def test_import_report_labels_late_historical_market_facts(tmp_path):
    payload = _cross_asset_payload()
    payload["as_of"] = "2026-09-25T15:00:00+00:00"
    payload["generated_at"] = payload["as_of"]
    payload["quality_summary"] = {"status": "degraded", "revision": "historical_backfill"}
    source, manifest = _source(tmp_path, payload)

    import_report(source, tmp_path / "site", manifest)

    markdown = (tmp_path / "site/artifacts/public/reports/2026-09-24-market-daily.md").read_text()
    assert "历史补报" in markdown
    assert "布伦特期货" in markdown
    payload["quality_summary"].pop("revision")
    source, manifest = _source(tmp_path, payload)
    with pytest.raises(ValueError, match="market date mismatch"):
        import_report(source, tmp_path / "other", manifest)


@pytest.mark.parametrize(
    "override",
    [
        {"observation_date": "2026-09-23"},
        {"unit": "USD/contract"},
        {"source_url": "https://example.test/price"},
    ],
)
def test_import_report_rejects_untrusted_cross_asset_fact(tmp_path, override):
    payload = _cross_asset_payload()
    payload["facts"][-2].update(override)
    source, manifest = _source(tmp_path, payload)

    with pytest.raises(ValueError, match="market date mismatch"):
        import_report(source, tmp_path / "site", manifest)


def test_import_report_rejects_incomplete_cross_asset_pair(tmp_path):
    payload = _cross_asset_payload()
    payload["facts"].remove(payload["facts"][-1])
    source, manifest = _source(tmp_path, payload)

    with pytest.raises(ValueError, match="market date mismatch"):
        import_report(source, tmp_path / "site", manifest)


def test_import_report_writes_source_backed_plain_text_from_public_fields(tmp_path):
    payload = _payload()
    payload.update(
        run_id="daily-2026-09-23",
        as_of="2026-09-24T08:30:00+00:00",
        generated_at="2026-09-24T08:30:00+00:00",
        facts=[
            {
                "id": "index.spx.change_percent",
                "unit": "percent",
                "value": -0.8,
                "quality": "reviewed",
                "source_url": "https://abcnews.com/amp/Business/example",
                "observation_date": "2026-09-23",
            },
            {
                "id": "treasury.10y.change_bp",
                "metric": "yield_change",
                "value": 15.0,
                "unit": "basis_points",
                "quality": "ok",
                "source_url": "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/all/202609?_format=csv&field_tdr_date_value_month=202609&page=&type=daily_treasury_yield_curve",
                "observation_date": "2026-09-23",
            },
        ],
        claims=[
            {
                "claim": "报道认为收益率上升带来压力；这不是已证明的唯一因果。",
                "evidence_ids": ["index.spx.change_percent"],
                "sources": ["https://abcnews.com/amp/Business/example"],
            }
        ],
        private_research_draft="private draft must not leak",
    )
    source, manifest = _source(tmp_path, payload)

    assert import_report(source, tmp_path / "site", manifest) == "2026-09-23"
    report = (tmp_path / "site/artifacts/public/reports/2026-09-23-market-daily.txt").read_text()
    assert "报告生成时间：2026-09-24T08:30:00+00:00" in report
    assert "一、美股市场表现" in report
    assert "标普 500 日涨跌：-0.80%（观测日 2026-09-23）" in report
    assert "五、市场驱动因素" in report
    assert "六、经济数据与美联储动态" in report
    assert "10 年期美债收益率日变动：+15.00 bp" in report
    assert "暂无经核实内容" not in report.split("六、经济数据与美联储动态")[1].split("七、公司新闻")[0]
    assert "八、其他已核实内容" in report
    assert "报道认为收益率上升带来压力；这不是已证明的唯一因果。" in report
    assert "https://abcnews.com/amp/Business/example" in report
    assert "private draft must not leak" not in report
    assert "市场有风险" in report


def test_plain_text_keeps_reviewed_drivers_and_company_news_in_own_sections(tmp_path):
    payload = _payload()
    payload["facts"].append(
        {
            "id": "macro.cpi_yoy",
            "value": 3.4,
            "source_url": "https://fred.stlouisfed.org/series/CPIAUCNS",
            "observation_date": "2026-08-01",
        }
    )
    payload["events"] = [
        {"id": "reviewed.1", "source_url": "https://example.test/close"},
        {"id": "reviewed.2", "source_url": "https://example.test/company"},
    ]
    payload["claims"] = [
        {
            "claim": "收盘报道将跌势与收益率上涨联系起来。",
            "evidence_ids": ["reviewed.1"],
            "sources": ["https://example.test/close"],
        },
        {
            "claim": "公司公告披露新的季度收入。",
            "evidence_ids": ["reviewed.2"],
            "sources": ["https://example.test/company"],
        },
    ]
    payload["sections"] = [
        {"key": "drivers", "title": "市场驱动因素", "claims": ["reviewed.1"], "facts": []},
        {"key": "company_news", "title": "公司新闻", "claims": ["reviewed.2"], "facts": []},
    ]
    source, manifest = _source(tmp_path, payload)
    import_report(source, tmp_path / "site", manifest)

    report = (tmp_path / "site/artifacts/public/reports/2026-09-19-market-daily.txt").read_text()
    assert "五、市场驱动因素" in report
    assert "七、公司新闻" in report
    assert report.index("五、市场驱动因素") < report.index("收盘报道将跌势")
    assert report.index("七、公司新闻") < report.index("公司公告披露")
    assert report.count("收盘报道将跌势") == 1
    assert report.count("公司公告披露") == 1

    markdown = (tmp_path / "site/artifacts/public/reports/2026-09-19-market-daily.md").read_text()
    headings = [
        f"## {title}"
        for title in (
            "美股市场表现",
            "市场驱动因素",
            "经济数据与美联储动态",
            "公司新闻",
            "主要个股",
        )
    ]
    assert all(heading in markdown for heading in headings)
    assert markdown.index("## 美股市场表现") < markdown.index("| 标普 500 |")
    assert markdown.index("## 经济数据与美联储动态") < markdown.index("CPI 同比")
    assert markdown.index("## 公司新闻") < markdown.index("公司公告披露")


def test_markdown_unclassified_claim_keeps_evidence_ids(tmp_path):
    source, manifest = _source(tmp_path, _payload())
    import_report(source, tmp_path / "site", manifest)
    markdown = (tmp_path / "site/artifacts/public/reports/2026-09-19-market-daily.md").read_text()
    assert "## 其他已核实内容" in markdown
    assert "证据：`index.spx.change_percent`" in markdown


def test_import_requires_matching_public_manifest_and_omits_private_fields(tmp_path):
    payload = _payload()
    payload["private_research_draft"] = "never publish this"
    payload["facts"][0]["private_passage"] = "not public"
    payload["events"] = [
        {
            "id": "reviewed.event.1",
            "title": "unreviewed private draft title",
            "actual": "unreviewed private draft actual",
            "source_url": "https://example.test/report",
        }
    ]
    payload["claims"][0]["evidence_ids"].append("reviewed.event.1")
    source, manifest = _source(tmp_path, payload)
    output = tmp_path / "site"
    assert import_report(source, output, manifest) == "2026-09-19"
    public = (output / "artifacts/public/data/market_daily_report.json").read_text()
    assert json.loads(public)["report_formats"] == ["md", "txt"]
    assert "private_research_draft" not in public
    assert "private_passage" not in public
    assert "unreviewed private draft title" not in public
    assert "unreviewed private draft actual" not in public
    assert json.loads(public)["events"] == [{"id": "reviewed.event.1"}]
    bad = json.loads(manifest.read_text())
    bad["publication"] = "private"
    manifest.write_text(json.dumps(bad))
    with pytest.raises(ValueError, match="public manifest"):
        import_report(source, output, manifest)


def test_import_rejects_rehashed_file_with_invalid_content_hash(tmp_path):
    source, manifest = _source(tmp_path, _payload())
    payload = json.loads(source.read_text())
    payload["claims"][0]["claim"] = "changed without content hash"
    source.write_text(json.dumps(payload))
    publication = json.loads(manifest.read_text())
    publication["report_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(publication))
    with pytest.raises(ValueError, match="content hash"):
        import_report(source, tmp_path / "site", manifest)


def test_import_accepts_private_snapshot_filename_bound_by_public_manifest(tmp_path):
    source, manifest = _source(tmp_path, _payload())
    snapshot = tmp_path / "input.json"
    snapshot.write_bytes(source.read_bytes())
    assert import_report(snapshot, tmp_path / "site", manifest) == "2026-09-19"


def test_import_rejects_duplicate_evidence_ids(tmp_path):
    payload = _payload()
    payload["facts"].append(dict(payload["facts"][0]))
    source, manifest = _source(tmp_path, payload)
    with pytest.raises(ValueError, match="duplicate"):
        import_report(source, tmp_path / "site", manifest)
