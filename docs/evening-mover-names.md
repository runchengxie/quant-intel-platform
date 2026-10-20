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
