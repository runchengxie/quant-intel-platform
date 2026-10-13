"""Point-in-time US macro facts from FRED's published observations."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from daily_messenger.etl.fetchers.fred import FredFetchError, FredObservation, fetch_observations

from .models import MarketFact
from .treasury import fetch_treasury_yield_observations
from .treasury import source_url as treasury_source_url
from .treasury_calendar import CALENDAR_SOURCE, CALENDAR_VERSION, expected_observation_date

NEW_YORK = ZoneInfo("America/New_York")
YIELD_SERIES = {"2y": "DGS2", "5y": "DGS5", "10y": "DGS10", "30y": "DGS30"}
MACRO_SERIES = {
    "cpi_yoy": "CPIAUCNS",
    "pce_yoy": "PCEPI",
    "unemployment_rate": "UNRATE",
    "payroll_change_thousands": "PAYEMS",
}


def _available_observations(
    series_id: str, as_of: datetime, *, days: int, max_age_days: int
) -> list[FredObservation]:
    market_date = as_of.astimezone(NEW_YORK).date()
    start = (market_date - timedelta(days=days)).isoformat()
    observations = fetch_observations(series_id, start=start)
    available = [row for row in observations if start <= row.date <= market_date.isoformat()]
    if len(available) < 2:
        raise FredFetchError("insufficient observations")
    if (market_date - datetime.fromisoformat(available[-1].date).date()).days > max_age_days:
        raise FredFetchError("stale observations")
    return available


def _year_ago_value(rows: list[FredObservation], current: FredObservation) -> float:
    year_ago = next(
        (row for row in rows if row.date[:7] == f"{int(current.date[:4]) - 1}{current.date[4:7]}"),
        None,
    )
    if year_ago is None or year_ago.value == 0:
        raise FredFetchError("prior-year observation unavailable")
    return year_ago.value


def _fact(
    fact_id: str,
    *,
    metric: str,
    series_id: str,
    value: float,
    previous: float | None,
    change: float | None,
    unit: str,
    observation_date: str,
    quality: str = "ok",
) -> MarketFact:
    read_time = datetime.now(UTC)
    return MarketFact(
        id=fact_id,
        metric=metric,
        instrument=series_id,
        value=round(value, 2),
        previous=round(previous, 2) if previous is not None else None,
        change=round(change, 2) if change is not None else None,
        unit=unit,
        source="FRED",
        source_url=f"https://fred.stlouisfed.org/series/{series_id}",
        source_time=read_time,
        retrieved_at=read_time,
        quality=quality,
        observation_date=observation_date,
    )


def _yield_observations(
    series_id: str, as_of: datetime, observation_date: date
) -> list[FredObservation]:
    rows = _available_observations(series_id, as_of, days=14, max_age_days=4)
    rows = [row for row in rows if row.date <= observation_date.isoformat()]
    if (
        len(rows) < 2
        or rows[-2].date
        != expected_observation_date(
            datetime.fromisoformat(rows[-1].date).date() - timedelta(days=1)
        ).isoformat()
    ):
        raise FredFetchError("adjacent Treasury observations unavailable")
    return rows


def _rate_facts(as_of: datetime) -> tuple[list[MarketFact], dict[str, dict[str, str]]]:
    facts: list[MarketFact] = []
    status: dict[str, dict[str, str]] = {}
    market_date = as_of.astimezone(NEW_YORK).date()
    observation_date = expected_observation_date(market_date)
    official_observations = fetch_treasury_yield_observations(observation_date)
    if official_observations is not None:
        read_time = datetime.now(UTC)
        facts = []
        for tenor in YIELD_SERIES:
            observation = official_observations[tenor]
            common = {
                "instrument": f"US_TREASURY_{tenor.upper()}",
                "source": "US Treasury",
                "source_url": treasury_source_url(observation_date),
                "source_time": read_time,
                "retrieved_at": read_time,
                "quality": "ok" if observation_date == market_date else "lagged",
                "observation_date": observation_date.isoformat(),
            }
            facts.extend(
                (
                    MarketFact(
                        id=f"treasury.{tenor}.level_percent",
                        metric="yield_level",
                        value=observation["level_percent"],
                        previous=observation["previous_level_percent"],
                        change=None,
                        unit="percent",
                        **common,
                    ),
                    MarketFact(
                        id=f"treasury.{tenor}.change_bp",
                        metric="yield_change",
                        value=observation["change_bp"],
                        previous=None,
                        change=observation["change_bp"],
                        unit="basis_points",
                        **common,
                    ),
                )
            )
        return facts, status
    for tenor, series_id in YIELD_SERIES.items():
        try:
            rows = _yield_observations(series_id, as_of, observation_date)
            current, previous = rows[-1].value, rows[-2].value
            facts.append(
                _fact(
                    f"treasury.{tenor}.level_percent",
                    metric="yield_level",
                    series_id=series_id,
                    value=current,
                    previous=previous,
                    change=None,
                    unit="percent",
                    observation_date=rows[-1].date,
                    quality="ok"
                    if rows[-1].date == as_of.astimezone(NEW_YORK).date().isoformat()
                    else "lagged",
                )
            )
            facts.append(
                _fact(
                    f"treasury.{tenor}.change_bp",
                    metric="yield_change",
                    series_id=series_id,
                    value=(current - previous) * 100,
                    previous=None,
                    change=(current - previous) * 100,
                    unit="basis_points",
                    observation_date=rows[-1].date,
                    quality="ok"
                    if rows[-1].date == as_of.astimezone(NEW_YORK).date().isoformat()
                    else "lagged",
                )
            )
        except (FredFetchError, ValueError):
            status[series_id] = {"quality": "degraded", "reason": "unavailable"}
    return facts, status


def rates_status(facts: list[MarketFact], market_date: date) -> dict[str, str]:
    rate_ids = {
        f"treasury.{tenor}.{metric}"
        for tenor in YIELD_SERIES
        for metric in ("change_bp", "level_percent")
    }
    rate_quality = "degraded"
    present = {fact.id: fact for fact in facts}
    if rate_ids <= present.keys():
        rate_quality = (
            "lagged" if any(present[fact_id].quality == "lagged" for fact_id in rate_ids) else "ok"
        )
    expected = expected_observation_date(market_date).isoformat()
    observed = min(
        (fact.observation_date or "" for fact in facts if fact.id in rate_ids), default=""
    )
    return {
        "quality": rate_quality,
        "session": "open" if expected == market_date.isoformat() else "closed",
        "expected_observation_date": expected,
        "observation_date": observed,
        "calendar_version": CALENDAR_VERSION,
        "calendar_source": CALENDAR_SOURCE,
        "reason": "holiday_reference"
        if expected != market_date.isoformat() and observed == expected
        else "expected_observation_fresh"
        if observed == expected
        else "observation_stale",
    }


def fetch_us_macro_facts(as_of: datetime) -> tuple[list[MarketFact], dict[str, dict[str, str]]]:
    """Return sourced facts and per-group status; unavailable series stay absent."""
    facts, status = _rate_facts(as_of)
    for name, series_id in MACRO_SERIES.items():
        try:
            rows = _available_observations(series_id, as_of, days=550, max_age_days=100)
            current = rows[-1]
            if name in {"cpi_yoy", "pce_yoy"}:
                value = (current.value / _year_ago_value(rows, current) - 1) * 100
                previous = None
                unit = "percent_yoy"
            elif name == "payroll_change_thousands":
                value = current.value - rows[-2].value
                previous = None
                unit = "thousand_persons"
            else:
                value = current.value
                previous = rows[-2].value
                unit = "percent"
            facts.append(
                _fact(
                    f"macro.{name}",
                    metric=name,
                    series_id=series_id,
                    value=value,
                    previous=previous,
                    change=None,
                    unit=unit,
                    observation_date=current.date,
                )
            )
        except (FredFetchError, ValueError):
            status[series_id] = {"quality": "degraded", "reason": "unavailable"}
    present = {fact.id: fact for fact in facts}
    status["rates"] = rates_status(facts, as_of.astimezone(NEW_YORK).date())
    status["macro"] = {
        "quality": "ok" if all(f"macro.{name}" in present for name in MACRO_SERIES) else "degraded"
    }
    return facts, status
