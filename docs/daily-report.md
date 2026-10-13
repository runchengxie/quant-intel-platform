
## Treasury observation calendar

US Treasury observations use a separate, offline, versioned SIFMA US bond calendar.
The reviewed schedule covers 2026–2027, with the 2025-12-31 early-close boundary;
uncovered dates fail closed until the calendar is reviewed and extended.
Early closes remain observation sessions (including 2026-04-03). On a closed
report day, collection requests the most recent expected session from the official
Treasury CSV, then falls back to FRED. Changes require the immediately preceding
expected session; missing observations are not bridged into a daily move.

Facts retain their true `observation_date` and `lagged` quality relative to the
stock report date. Rates status carries expected/actual dates, session, calendar
version and source. A fresh closed-day reference is labelled `holiday_reference`;
it is not a report-day return and does not create a same-day chart bar. Older
references remain incomplete. The installed package also includes the versioned
`data/treasury_sessions_v1.json` expected-date artifact so read-only consumers
need neither a child process nor a network request. The reviewed schedule is available through:

```bash
python -m daily_messenger.daily_report.treasury_calendar --date 2026-10-12
```

A Treasury-only correction can be staged through the installed owner CLI:

```bash
REPORT_DIR="${MARKET_DAILY_REPORT_OUT:-${DATA_PLATFORM_ROOT:?}/reports/market-intel/daily_report}"
python -m daily_messenger.daily_report.treasury_revision \
  --input "$REPORT_DIR/daily_report.json" \
  --manifest "$REPORT_DIR/publication.json" \
  --output "$DATA_PLATFORM_ROOT/reports/market-intel/treasury_revisions/20261012-reference"
```

The output must be new and outside source repositories. The owner preserves the
parent bytes, non-Treasury facts, news and research, records original/revised
cutoffs and hashes in a private receipt, and emits a validated candidate.
Promotion and website publication remain deployment-owned operations.
Sources: https://www.sifma.org/resources/general/holiday-schedule and
https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve&field_tdr_date_value_month=202610
