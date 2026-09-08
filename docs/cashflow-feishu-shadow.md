# 现金流策略飞书 Shadow 推送

现金流推送只接受 `strategy_app.cashflow.selection.v1` 产物，并强制要求：

- `status=passed`；
- `research_only=true`；
- `eligible_for_live=false`；
- source date、signal date 与命令参数一致；
- 必须提供 `strategy_pipeline.cashflow.publication.v1`，且 `selection_sha256` 与目标文件一致的 publication receipt；
- 目标权重非负、无重复股票且总和为 100%；
- 显式传入至少一个 Feishu 测试群 `--chat-id`。

运行示例：

```bash
uv run a-share-daily cashflow-delivery \
  --selection /path/to/selection.json \
  --source-date 20260904 \
  --signal-date 20260907 \
  --publication-receipt /path/to/publication-receipt.json \
  --chat-id oc_test_group \
  --receipt /path/to/cashflow-delivery-receipt.json
```

发送使用现有 `lark-cli` bot 通道。幂等键绑定策略、`policy`、signal date、目标群和 artifact content hash；重复运行会从匹配的 delivery receipt 复用成功结果，不重复发送。

当前适配器不读取默认客户群，也不支持正式生产群配置。`--dry-run` 只生成状态为 `dry_run` 的回执，不代表消息已送达。

## 定时 Shadow 桥接

`scripts/run_cashflow_shadow.sh` 是部署桥接脚本，不包含策略逻辑。它要求使用外部 `~/.config/market-intel/cashflow-shadow.env`，显式配置路径和测试群 ID，例如：

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

可选的 `cashflow-feishu-shadow.timer` 在工作日 06:15 运行。只有向 `setup_cron.sh --layer2` 显式传入 `CASHFLOW_SHADOW_ENABLE=1` 时才会安装，默认部署不会启用。真实发送还要求 `CASHFLOW_SEND_CONFIRMATION=I_UNDERSTAND_TEST_GROUP_ONLY`。

设置 `CASHFLOW_DATA_ROOT` 后，桥接脚本会在调用编排器之前，从最新完整且已封存的数据版本刷新 PIT audit receipt。被阻断的 audit 会保留并传递给下游，但不会成为可用的特征输入。
