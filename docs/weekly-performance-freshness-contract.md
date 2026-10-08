# Weekly performance freshness

`weekly_basket.performance.v2` may carry a `freshness` object to establish that
its NAV ends at the trading session immediately before the report date. This
allows a report after a market holiday without relaxing missing-session checks.
The research provider owns calendar selection and computes the expected session;
the report consumer validates the evidence rather than importing research code.

```json
{
  "freshness": {
    "method": "prior_open_session",
    "report_date": "20261008",
    "expected_session": "20260930",
    "calendar_sha256": "<64 lowercase hexadecimal characters>"
  }
}
```

Both dates must be valid `YYYYMMDD` dates. The evidence report date must equal the
artifact and requested report dates. The expected session must precede the report
date and equal the final NAV date. Benchmark dates must still align with NAV.
`calendar_sha256` identifies the calendar bytes used by the provider. The existing
canonical `artifact_sha256` covers the entire freshness object as well as the
other artifact fields; it is an integrity checksum, not an authenticity signature.

An absent freshness field retains the existing maximum age of seven calendar
days. An explicit null or malformed object fails validation, without falling back
to the older rule. Existing benchmark, execution audit, metrics, schema and hash
requirements remain in effect. Consumers do not independently verify calendar
contents, so the provider must validate calendar coverage and reject performance
that misses the expected open session before publishing.
