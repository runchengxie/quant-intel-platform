# Evening mover names

The evening review retains the original top-five gainers and decliners selection,
sorting, and return values. Each row now carries `name` alongside `ts_code`.
Existing nonempty daily names take precedence.

When daily names are absent, the report reads the data owner's existing
`assets/tushare/a_share/instruments/a_share_all_instruments_latest.parquet` under
the explicitly configured data root. It requires a complete
`market-data-platform.tushare-reference.v1` receipt, a matching file SHA-256, and
a reference date no later than the report date. Conflicting duplicate codes,
empty names, unavailable files, or invalid receipts leave the code visible
without inventing a name. This reference is a display mapping, not a historical
point-in-time name reconstruction. No provider request is added.

Markdown entries use `CODE Name(+1.00%)`; absent names retain the legacy
`CODE(+1.00%)` form. Name delimiters and markup are escaped. Pages must consume
both forms and escape decoded names when rendering HTML/SVG. Deploying the
producer and Pages consumer is a separate action; local source changes do not
change scheduled reports or replay a previous delivery.


## Turnover and money flow display identity

The turnover TOP10 Markdown table uses four columns in this order:
`| 名称 | 代码 | 成交额(亿) | 涨跌 |`. Codes retain their full exchange suffix
(for example `300308.SZ`). Names follow the same daily-row-first, validated
instrument-reference fallback as movers; unavailable names display `N/A`.
Ranking, amounts, percentage precision, dates, and public artifact identifiers
are unchanged. Consumers must retain support for the earlier three-column table.

Money-flow public chart labels use `Name CODE.market`, and the PNG puts that
same name above the full code on two lines, with money amounts displayed to two
decimal places. Source observations and units are
unchanged. A current report must be regenerated from frozen owner inputs through
`market-public-refresh`, then imported using the normal public snapshot flow;
editing historical report bytes or fetching missing names is not a replay.
