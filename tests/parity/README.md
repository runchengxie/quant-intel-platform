# Quant parity runner

`run_parity.py` compares JSON artifacts already materialized by the old and
new implementations. It writes a dated comparison manifest and exits nonzero
when an artifact is missing or a mandatory field differs.

```bash
uv run python -m parity.run_parity \
  --source-date 20260908 \
  --signal-date 20260909 \
  --old-root /path/to/old/artifacts \
  --new-root /path/to/new/artifacts \
  --output-root docs/superpowers/artifacts/parity-runs \
  --old-data-snapshot-id snapshot-20260908 \
  --new-data-snapshot-id snapshot-20260908
```

Runtime timestamps, message IDs, and run IDs are ignored by default. Add
`--ignore-field FIELD` only for a documented, intentional difference.
The two data snapshot IDs must match for a run to be eligible for the
five-day parity count; mismatches are recorded and return a nonzero status.
Use `--old-commit` and `--new-commit` when the artifact roots are not Git
checkouts and their implementation revisions cannot be discovered locally.

## Frozen A-share freshness input

Historical replay must not let the new pipeline read the current `latest`
dataset state as a substitute for the historical run. Create a replay-only
freshness receipt from the old manifest (the receipt must contain the original
`freshness` object plus `schema_version: a_share.freshness.snapshot.v1` and a
stable `snapshot_id`) and set:

```bash
export A_SHARE_FRESHNESS_SNAPSHOT=/path/to/freshness-YYYYMMDD.json
```

The loader requires the receipt `target_date` to match the pipeline date and
fails closed for an unknown schema or malformed contracts. The variable is
unset in production; normal production runs continue to inspect the canonical
data root.
