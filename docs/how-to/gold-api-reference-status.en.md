# Gold API reference integration status

## Verified on 2026-10-01

The private `gold_api` credential successfully authenticated XAU and XAG OHLC
queries. A deliberately invalid key returned HTTP 401. Live requests and the
private credential file are not part of the repository or CI.

The provider's [API documentation](https://gold-api.com/llms.txt) defines OHLC
over a requested segment. `startTimestamp` and `endTimestamp` echo the requested
boundaries; they are not the timestamp of the last price observation. A segment
ending in the future can return HTTP 200 while still containing partial data.
An entirely future segment returned HTTP 404 in the bounded diagnostic probe.
The provider's [homepage](https://gold-api.com/) labels its displayed gold price
as USD per ounce. It does not identify the underlying feed, establish the exact
XAG unit, or supply actual observation timestamps for historical segment closes.

The private reader `daily_messenger.daily_report.gold_reference` therefore:

- rejects future, unordered, timezone-naive and subsecond boundaries;
- validates exact returned bounds, finite positive numbers and OHLC ordering;
- uses only XAU/XAG and disables redirects to avoid forwarding the API key;
- exposes only safe error classifications, never raw HTTP bodies;
- leaves `actual_quote_time` unknown rather than inventing it from request bounds.

## Not enabled in production

This reader does not produce public facts, change completeness scoring, invoke
model research, or send Feishu messages. It must not be added to the five-minute
retry timer without persistent caching and quota controls: the provider documents
a shared free historical/OHLC limit of ten requests per hour.

Before public integration, obtain a verifiable quotation-unit and underlying
instrument/data-source definition, and establish a policy for segment freshness
when the last observation timestamp is absent. Commercial API use is permitted
by the provider's [terms](https://gold-api.com/terms), but that does not establish
whether the reference is spot, futures, or an exchange settlement.

Keep any verified reference series separate from COMEX dated-contract facts.
Never use it to silently clear the existing gold/silver futures completeness gaps.
