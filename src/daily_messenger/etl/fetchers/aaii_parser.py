"""Conservative current-survey parsing; averages are never survey observations."""

import datetime as dt
import re
from html.parser import HTMLParser


class ArticleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.publication: str | None = None

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "meta" and values.get("property", values.get("name")) in {
            "article:published_time",
            "datePublished",
        }:
            self.publication = values.get("content")
        if tag == "time" and values.get("itemprop") == "datePublished":
            self.publication = values.get("datetime")


def article(html: str) -> ArticleText:
    parsed = ArticleText()
    parsed.feed(html)
    return parsed


def parse_metrics(html: str) -> dict[str, float] | None:
    text = " ".join(article(html).parts).replace("’", "'")
    marker = re.search(r"This week's\s+(?:Sentiment\s+)?Survey results\s*:", text, re.I)
    if marker is None:
        return None
    block = re.split(r"Historical averages\s*:", text[marker.end() :], flags=re.I)[0]
    values = []
    for label in ("Bullish", "Neutral", "Bearish"):
        matches = re.findall(rf"\b{label}\s*:\s*(\d+(?:\.\d+)?)\s*%", block, re.I)
        if len(matches) != 1:
            return None
        values.append(float(matches[0]))
    bull, neutral, bear = values
    if any(value < 0 or value > 100 for value in values) or abs(sum(values) - 100) > 0.3:
        return None
    return {
        "bullish_pct": bull,
        "neutral_pct": neutral,
        "bearish_pct": bear,
        "bull_bear_spread": round(bull - bear, 2),
    }


def survey_week(html: str) -> str | None:
    text = " ".join(article(html).parts)
    match = re.search(r"Week ending\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})", text, re.I)
    if not match:
        return None
    try:
        return dt.datetime.strptime(match[1], "%B %d, %Y").date().isoformat()
    except ValueError:
        return None


def publication_date(html: str, feed_date: str | None) -> str | None:
    from email.utils import parsedate_to_datetime

    dates = []
    try:
        if feed_date:
            dates.append(parsedate_to_datetime(feed_date).date().isoformat())
        raw = article(html).publication
        if raw:
            dates.append(dt.datetime.fromisoformat(raw.replace("Z", "+00:00")).date().isoformat())
    except (TypeError, ValueError, OverflowError):
        return None
    return dates[0] if dates and len(set(dates)) == 1 else None
