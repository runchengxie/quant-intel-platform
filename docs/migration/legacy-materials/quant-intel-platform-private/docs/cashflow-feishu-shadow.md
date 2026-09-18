# ç°éæµç­ç¥é£ä¹¦ Shadow æ¨é

ç°éæµæ¨éåªæ¥å `strategy_app.cashflow.selection.v1` äº§ç©ï¼å¹¶å¼ºå¶è¦æ±ï¼

- `status=passed`ï¼
- `research_only=true`ï¼
- `eligible_for_live=false`ï¼
- source dateãsignal date ä¸å½ä»¤åæ°ä¸è´ï¼
- å¿é¡»æä¾ `strategy_pipeline.cashflow.publication.v1` ä¸ `selection_sha256` ä¸ç®æ æä»¶ä¸è´ç publication receiptï¼
- ç®æ æééè´ãæ éå¤è¡ç¥¨ä¸æ»åä¸º 100%ï¼
- æ¾å¼ä¼ å¥è³å°ä¸ä¸ª Feishu æµè¯ç¾¤ `--chat-id`ã

è¿è¡ç¤ºä¾ï¼

```bash
uv run a-share-daily cashflow-delivery \
  --selection /path/to/selection.json \
  --source-date 20260904 \
  --signal-date 20260907 \
  --publication-receipt /path/to/publication-receipt.json \
  --chat-id oc_test_group \
  --receipt /path/to/cashflow-delivery-receipt.json
```

åéä½¿ç¨ç°æ `lark-cli` bot ééãå¹ç­é®ç»å®ç­ç¥ãpolicyãsignal dateãç®æ ç¾¤å artifact content hashï¼éå¤è¿è¡ä¼ä»å¹éç delivery receipt å¤ç¨æåç»æï¼ä¸éå¤åéã

å½å adapter ä¸è¯»åé»è®¤å®¢æ·ç¾¤ï¼ä¹ä¸æ¯ææ­£å¼çäº§ç¾¤éç½®ã`--dry-run` åªçæç¶æä¸º `dry_run` çåæ§ï¼ä¸ä»£è¡¨æ¶æ¯å·²éè¾¾ã

## Scheduled shadow bridge

`scripts/run_cashflow_shadow.sh` is the deployment bridge; it does not contain
strategy logic. It requires an external
`~/.config/market-intel/cashflow-shadow.env` with explicit paths and test chat
IDs, for example:

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

The optional `cashflow-feishu-shadow.timer` runs at 06:15 on weekdays. It is
installed only when `CASHFLOW_SHADOW_ENABLE=1` is explicitly supplied to
`setup_cron.sh --layer2`; the default deployment does not enable it. Real send
also requires `CASHFLOW_SEND_CONFIRMATION=I_UNDERSTAND_TEST_GROUP_ONLY`.

When `CASHFLOW_DATA_ROOT` is set, the bridge refreshes the PIT audit receipt
from the newest complete sealed vintage before invoking the orchestrator. A
blocked audit is retained and passed downstream; it never becomes a usable
feature input.
