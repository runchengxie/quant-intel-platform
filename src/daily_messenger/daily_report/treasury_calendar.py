"""Reviewed US bond sessions; early closes still require an observation.

Source: https://www.sifma.org/resources/general/holiday-schedule
Reviewed 2026-10-13 for the 2026/2027 US schedules. The prior-year boundary
includes the documented 2025-12-31 early close. Uncovered dates fail closed.
"""

from __future__ import annotations

from datetime import date, timedelta

CALENDAR_VERSION = "sifma.us-bonds.2026-2027.v1"
CALENDAR_SOURCE = "https://www.sifma.org/resources/general/holiday-schedule"
START = date(2025, 12, 24)
END = date(2027, 12, 31)
CLOSURES = frozenset(
    date.fromisoformat(value)
    for value in (
        "2025-12-25",
        "2026-01-01",
        "2026-01-19",
        "2026-02-16",
        "2026-05-25",
        "2026-06-19",
        "2026-07-03",
        "2026-09-07",
        "2026-10-12",
        "2026-11-11",
        "2026-11-26",
        "2026-12-25",
        "2027-01-01",
        "2027-01-18",
        "2027-02-15",
        "2027-03-26",
        "2027-05-31",
        "2027-06-18",
        "2027-07-05",
        "2027-09-06",
        "2027-10-11",
        "2027-11-11",
        "2027-11-25",
        "2027-12-24",
    )
)


def is_treasury_session(day: date) -> bool:
    if not START <= day <= END:
        raise ValueError("Treasury calendar coverage unavailable")
    return day.weekday() < 5 and day not in CLOSURES


def expected_observation_date(day: date) -> date:
    while not is_treasury_session(day):
        day -= timedelta(days=1)
    return day


def session_metadata(day: date) -> dict[str, str]:
    expected = expected_observation_date(day)
    return {
        "schema_version": "market_intel.treasury_session.v1",
        "report_date": day.isoformat(),
        "session": "open" if expected == day else "closed",
        "expected_observation_date": expected.isoformat(),
        "calendar_version": CALENDAR_VERSION,
        "calendar_source": CALENDAR_SOURCE,
    }


def main() -> None:
    import argparse
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, type=date.fromisoformat)
    args = parser.parse_args()
    print(json.dumps(session_metadata(args.date), sort_keys=True))


if __name__ == "__main__":
    main()
