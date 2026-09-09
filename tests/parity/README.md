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
  --output-root docs/superpowers/artifacts/parity-runs
```

Runtime timestamps, message IDs, and run IDs are ignored by default. Add
`--ignore-field FIELD` only for a documented, intentional difference.
