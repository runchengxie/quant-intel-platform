"""Daily Treasury par-yield changes from the US Treasury's public CSV."""

from __future__ import annotations

import csv
import io
import math
from datetime import date, datetime, timedelta

import requests

TREASURY_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "daily-treasury-rates.csv/all/{month}?_format=csv&field_tdr_date_value_month={month}"
    "&page=&type=daily_treasury_yield_curve"
)
TENORS = {"2y": "2 Yr", "5y": "5 Yr", "10y": "10 Yr", "30y": "30 Yr"}


def source_url(market_date: date) -> str:
    return TREASURY_URL.format(month=market_date.strftime("%Y%m"))


def _rows(csv_text: str) -> dict[date, dict[str, float]]:
    result: dict[date, dict[str, float]] = {}
    for row in csv.DictReader(io.StringIO(csv_text)):
        try:
            day = datetime.strptime(row["Date"], "%m/%d/%Y").date()
            rates = {tenor: float(row[column]) for tenor, column in TENORS.items()}
        except (KeyError, TypeError, ValueError):
            continue
        if all(math.isfinite(value) for value in rates.values()):
            result[day] = rates
    return result


def fetch_treasury_yield_observations(market_date: date) -> dict[str, dict[str, float]] | None:
    """Return same-day levels and prior-observation moves from one official curve fetch."""
    try:
        response = requests.get(source_url(market_date), timeout=45)
        response.raise_for_status()
        observations = _rows(response.text)
        if market_date.day <= 4:
            prior_month = market_date.replace(day=1) - timedelta(days=1)
            previous = requests.get(source_url(prior_month), timeout=45)
            previous.raise_for_status()
            observations.update(_rows(previous.text))
    except (requests.RequestException, csv.Error):
        return None
    if market_date not in observations:
        return None
    previous_days = [day for day in observations if day < market_date]
    if not previous_days:
        return None
    prior = observations[max(previous_days)]
    current = observations[market_date]
    return {
        tenor: {
            "level_percent": current[tenor],
            "previous_level_percent": prior[tenor],
            "change_bp": round((current[tenor] - prior[tenor]) * 100, 2),
        }
        for tenor in TENORS
    }


def fetch_treasury_yield_changes(market_date: date) -> dict[str, float] | None:
    """Return same-day basis-point moves, or None when observations are incomplete."""
    observations = fetch_treasury_yield_observations(market_date)
    if observations is None:
        return None
    return {tenor: row["change_bp"] for tenor, row in observations.items()}
