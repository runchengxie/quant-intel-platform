[Chinese version](cashflow-feishu-shadow.md)

# Cashflow strategy shadow delivery to Feishu

Cashflow delivery accepts only a `strategy_app.cashflow.selection.v1` artifact and checks that:

- `status=passed`
- `research_only=true`
- `eligible_for_live=false`
- Source date and signal date match the command arguments
- A `strategy_pipeline.cashflow.publication.v1` receipt is present and its `selection_sha256` matches the target file
- Target weights are non-negative, stock symbols are unique, and weights sum to 100%
- At least one Feishu test-group `--chat-id` is explicitly supplied

## Example

```bash
uv run a-share-daily cashflow-delivery \
  --selection /path/to/selection.json \
  --source-date 20260904 \
  --signal-date 20260907 \
  --publication-receipt /path/to/publication-receipt.json \
  --chat-id oc_test_group \
  --receipt /path/to/cashflow-delivery-receipt.json
```

Delivery uses the existing `lark-cli` bot channel. Its idempotency key combines the strategy, signal date, target group, and artifact content hash. A repeated run reuses a matching delivery receipt and does not send the message again.

The adapter does not read default customer groups and does not support production-group configuration. `--dry-run` writes a receipt with status `dry_run`; it does not mean a message was delivered.

## Scheduled shadow bridge

`scripts/run_cashflow_shadow.sh` in `quant-intel-deploy` is a deployment bridge and contains no strategy logic. Configure explicit paths and test-group IDs externally before running it, for example:

```bash
QUANT_RESEARCH_ROOT=/home/richard/code/quant/quant-research
QUANT_PLATFORM_ROOT=/home/richard/code/quant/quant-platform
CASHFLOW_TRADE_CALENDAR=/path/to/trade_calendar.parquet
CASHFLOW_FEATURES=/path/to/pit_features.parquet
CASHFLOW_FEATURES_RECEIPT=/path/to/pit_features.receipt.json
CASHFLOW_PIT_AUDIT=/path/to/cashflow_pit_audit.json
CASHFLOW_DATA_ROOT=/path/to/market-data-platform
CASHFLOW_OUTPUT_ROOT=/path/to/cashflow-runs
CASHFLOW_PUBLICATION_ROOT=/path/to/cashflow-publications
CASHFLOW_ROLLOUT_LEDGER=/path/to/cashflow-shadow-rollout.json
CASHFLOW_DELIVERY_RECEIPT=/path/to/cashflow-delivery-receipt.json
CASHFLOW_CHAT_IDS=oc_test_group
CASHFLOW_SEND=0
```

The optional `cashflow-feishu-shadow.timer` runs at 06:15 on weekdays. It is installed only when `CASHFLOW_SHADOW_ENABLE=1` is explicitly set and `setup_cron.sh --layer2` is run; it is disabled by default.

When `CASHFLOW_DATA_ROOT` is set, the bridge first creates a point-in-time audit receipt from the latest complete data, then calls the orchestrator. If the audit fails, its result is retained and passed downstream but is not treated as usable features.
