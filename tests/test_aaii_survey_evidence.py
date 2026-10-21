"""Minimal reconstructed official text cases; not captured production HTML."""

import sys
from types import SimpleNamespace

import pytest

from a_share_daily import cross_market, fallback_fetch
from daily_messenger.etl.fetchers import aaii_sentiment as aaii

ARTICLE = """<h1>Survey</h1><time itemprop="datePublished" datetime="2026-10-15T08:00:00-04:00"></time>
<p>Week ending October 14, 2026</p>
<p>This week's Sentiment Survey results:</p>
<p>Bullish: 38.7%</p><p>Neutral: 19.7%</p><p>Bearish: 41.6%</p>
<p>Historical averages:</p><p>Bullish: 37.5%</p><p>Neutral: 31.0%</p><p>Bearish: 31.5%</p>"""
URL = "https://www.aaii.com/latest/article/553747-aaii-sentiment-survey-pessimism-rises"


def test_historical_averages_before_results_are_never_current():
    historical = "<p>Historical averages: Bullish: 37.5% Neutral: 31.0% Bearish: 31.5%</p>"
    assert aaii._parse_article(historical + ARTICLE)["bullish_pct"] == 38.7


def test_only_historical_averages_are_rejected():
    assert (
        aaii._parse_article("Historical averages: Bullish: 37.5% Neutral: 31.0% Bearish: 31.5%")
        is None
    )


def install_fetch(monkeypatch, html, pubdate="Thu, 15 Oct 2026 08:00:00 -0400"):
    rss = f"<rss><channel><item><title>AAII Sentiment Survey</title><link>{URL}</link><pubDate>{pubdate}</pubDate></item></channel></rss>"

    def get(url, **_kwargs):
        return SimpleNamespace(
            text=rss if url == aaii.RSS_URL else html, raise_for_status=lambda: None
        )

    monkeypatch.setattr(aaii, "_init_session", lambda: SimpleNamespace(get=get))


def test_fetch_preserves_distinct_survey_week_and_publication(monkeypatch):
    install_fetch(monkeypatch, ARTICLE)
    payload, status = aaii.fetch()
    assert status.ok
    row = payload["aaii"]
    assert row["week"] == "2026-10-14"
    assert row["survey_week_ending"] == "2026-10-14"
    assert row["publication_date"] == "2026-10-15"
    assert row["link"] == URL


def test_no_date_never_defaults_to_today(monkeypatch):
    install_fetch(
        monkeypatch,
        ARTICLE.replace(
            '<time itemprop="datePublished" datetime="2026-10-15T08:00:00-04:00"></time>', ""
        ),
        pubdate="",
    )
    assert not aaii.fetch()[1].ok


def test_cross_market_keeps_source_provenance(monkeypatch):
    row = {
        "week": "2026-10-14",
        "publication_date": "2026-10-15",
        "survey_week_ending": "2026-10-14",
        "link": URL,
        "source": "aaii",
        "bullish_pct": 38.7,
        "neutral_pct": 19.7,
        "bearish_pct": 41.6,
        "bull_bear_spread": -2.9,
    }
    monkeypatch.setattr(aaii, "fetch", lambda: ({"aaii": row}, SimpleNamespace(ok=True)))
    assert cross_market._fetch_aaii() == row


@pytest.mark.parametrize("publication", [None, "bad-date", "2026-10-21"])
def test_unknown_or_future_aaii_publication_blocks_historical_ready(monkeypatch, publication):
    data = cross_market._annotate_freshness(
        {
            "date": "20261020",
            "aaii_sentiment": {
                "week": "2026-10-14",
                "publication_date": publication,
                "link": URL,
                "bullish_pct": 38.7,
            },
        },
        "20261020",
    )
    assert data["_freshness_warnings"]
    monkeypatch.setattr(fallback_fetch, "run", lambda *_a, **_kw: data)
    monkeypatch.setattr(sys, "argv", ["fallback_fetch", "--date", "20261020"])
    assert fallback_fetch.main() == 1


def test_proven_prior_publication_passes_historical_date_gate():
    data = cross_market._annotate_freshness(
        {
            "date": "20261020",
            "aaii_sentiment": {
                "week": "2026-10-14",
                "publication_date": "2026-10-15",
                "link": URL,
                "bullish_pct": 38.7,
            },
        },
        "20261020",
    )
    assert not data.get("_freshness_warnings")


@pytest.mark.parametrize(
    "body",
    [
        "This week's Sentiment Survey results: Bullish: 38.7% Neutral: 19.7%",
        "This week's Sentiment Survey results: Bullish: 138.7% Neutral: 19.7% Bearish: 41.6%",
        "This week's Sentiment Survey results: Bullish: 38.7% Bullish: 40% Neutral: 19.7% Bearish: 41.6%",
        "This week's Sentiment Survey results: Bullish: 10% Neutral: 10% Bearish: 10%",
    ],
)
def test_incomplete_duplicate_or_invalid_survey_rejected(body):
    assert aaii._parse_article(body) is None


def test_conflicting_publication_evidence_is_rejected(monkeypatch):
    install_fetch(monkeypatch, ARTICLE, pubdate="Fri, 16 Oct 2026 08:00:00 -0400")
    assert not aaii.fetch()[1].ok


def test_unproven_week_is_not_invented(monkeypatch):
    install_fetch(monkeypatch, ARTICLE.replace("Week ending October 14, 2026", ""))
    payload, status = aaii.fetch()
    assert status.ok
    assert payload["aaii"]["week"] is None
    assert payload["aaii"]["survey_week_ending"] is None
    assert payload["aaii"]["publication_date"] == "2026-10-15"


@pytest.mark.parametrize("week", ["2026-10-21", "not-a-date"])
def test_future_or_invalid_explicit_survey_week_warns(week):
    data = cross_market._annotate_freshness(
        {
            "date": "20261020",
            "aaii_sentiment": {
                "publication_date": "2026-10-15",
                "survey_week_ending": week,
                "link": URL,
                "bullish_pct": 38.7,
            },
        },
        "20261020",
    )
    assert data.get("_freshness_warnings")


def test_survey_week_after_publication_is_rejected(monkeypatch):
    install_fetch(monkeypatch, ARTICLE.replace("October 14, 2026", "October 21, 2026"))
    assert not aaii.fetch()[1].ok
