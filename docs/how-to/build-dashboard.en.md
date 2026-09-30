# Build the web dashboard

[中文页面](build-dashboard.md)

## Quick start

Prepare the daily-report data under `out/`, then run:

```bash
uv run dm dashboard
```

The command writes `out/web_dashboard.html` by default. Open that file in a browser.

## Choose an output path

```bash
uv run dm dashboard \
  --out /tmp/market-intel-dashboard.html \
  --snapshot-dir data-snapshots/latest
```

`--snapshot-dir` selects the cross-market and other snapshot location. Without a snapshot, the dashboard can still display available report data, while some sections show a missing-data state.

## Add a state panel

If a market-state CSV is available, pass it as an optional input:

```bash
uv run dm dashboard \
  --state-panel out/market_state_panel.csv
```

The state panel does not change core report data.

## Troubleshooting

If the page is empty, check that `out/` contains daily-report JSON, that `--snapshot-dir` points to the intended directory, and that an old production directory was not selected accidentally. See [Web dashboard](../web-dashboard.md) for field and input formats and [Artifact contracts](../contracts.md) for the report schema.
