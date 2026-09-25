from datetime import date

from daily_messenger.daily_report.treasury import (
    fetch_treasury_yield_changes,
    fetch_treasury_yield_observations,
)

CSV = (
    'Date,"2 Yr","5 Yr","10 Yr","30 Yr"\n'
    "09/23/2026,4.85,4.99,5.11,5.40\n"
    "09/22/2026,4.71,4.83,4.96,5.29\n"
)


class Response:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


def test_official_csv_computes_same_day_basis_point_moves(monkeypatch):
    monkeypatch.setattr(
        "daily_messenger.daily_report.treasury.requests.get",
        lambda *_args, **_kwargs: Response(CSV),
    )
    assert fetch_treasury_yield_changes(date(2026, 9, 23)) == {
        "2y": 14.0,
        "5y": 16.0,
        "10y": 15.0,
        "30y": 11.0,
    }


def test_official_csv_returns_current_and_previous_yield_levels(monkeypatch):
    monkeypatch.setattr(
        "daily_messenger.daily_report.treasury.requests.get",
        lambda *_args, **_kwargs: Response(CSV),
    )
    observations = fetch_treasury_yield_observations(date(2026, 9, 23))
    assert observations["10y"] == {
        "level_percent": 5.11,
        "previous_level_percent": 4.96,
        "change_bp": 15.0,
    }
    assert observations["2y"]["level_percent"] == 4.85


def test_official_csv_uses_previous_month_for_first_day_of_month(monkeypatch):
    requested = []
    current_month = 'Date,"2 Yr","5 Yr","10 Yr","30 Yr"\n09/01/2026,4.85,4.99,5.11,5.40\n'
    previous_month = 'Date,"2 Yr","5 Yr","10 Yr","30 Yr"\n08/31/2026,4.71,4.83,4.96,5.29\n'

    def get(url, **_kwargs):
        requested.append(url)
        return Response(current_month if "202609" in url else previous_month)

    monkeypatch.setattr("daily_messenger.daily_report.treasury.requests.get", get)
    observations = fetch_treasury_yield_observations(date(2026, 9, 1))
    assert observations["10y"] == {
        "level_percent": 5.11,
        "previous_level_percent": 4.96,
        "change_bp": 15.0,
    }
    assert len(requested) == 2


def test_official_csv_does_not_present_previous_day_as_current(monkeypatch):
    monkeypatch.setattr(
        "daily_messenger.daily_report.treasury.requests.get",
        lambda *_args, **_kwargs: Response(CSV.replace("09/23/2026,4.85,4.99,5.11,5.40\n", "")),
    )
    assert fetch_treasury_yield_changes(date(2026, 9, 23)) is None
