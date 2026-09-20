# 2026-09-08 frozen production-input replay

## Result

The replay used `quant-intel-platform` main at `9b40213` and matched the
production input identity `historical-20260908`.

- New pipeline completed successfully.
- Dashboard generation completed; no dashboard error or failed chart.
- Cross-market data was loaded from the exact-date frozen snapshot, not live
  network data.
- The comparator reported six differences, all under `topic_summary`.

## Remaining differences

The old production manifest records a `topic_summary.json` from source date
`20260907` and marks it invalid for the requested `20260908` report. The new
pipeline was given the corrected Watch20 artifact for source date `20260908`
and signal date `20260909`, producing five topics. The six differences are the
expected consequence of comparing the corrected input with the stale old
artifact:

- `topic_summary.ok`
- `topic_summary.reason`
- `topic_summary.source_date`
- `topic_summary.signal_date`
- `topic_summary.topic_count`
- `topic_summary.topic_summary_json`

No market-data, chart-status, chart-path, or cross-market business-field
difference remained after freezing the old cross-market payload.

## Input and comparison sources

- A-share freshness receipt: generated from
  `reports/market-intel/a_share_daily/.morning_pipeline_20260908.json`, with
  schema `a_share.freshness.snapshot.v1` and snapshot ID
  `historical-20260908`.
- A-share data overlay: `/tmp/a-share-report-snapshot-20260908-real`, built by
  the merged `quant-market-data-platform` snapshot builder.
- Corrected Watch20 input:
  `strategy_outputs/watchlist20/runs/20260909_20260909T010801Z_fd59c76e/topic_summary.json`.
- Cross-market input: the old production payload, normalized only for replay
  date and freshness metadata so the snapshot loader would not fall back to
  live fetching.
- Comparator: `tests/parity/run_parity.py`, with only documented runtime,
  path, and snapshot metadata fields ignored.

The old root used for this run did not contain standalone `manifest.json` or
`weekly_recap.meta.json`; those are artifact-materialization gaps in the old
delivery root, not new-pipeline failures. A final five-day gate still requires
materializing those old artifacts and replaying four additional dates with
date-pinned cross-market and Watch20 inputs.
