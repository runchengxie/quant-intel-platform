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
