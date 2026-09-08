# 现金流策略飞书影子投递

现金流投递只接收 `strategy_app.cashflow.selection.v1` 产物，并检查以下条件：

- `status=passed`
- `research_only=true`
- `eligible_for_live=false`
- source date、signal date 与命令参数一致
- 提供 `strategy_pipeline.cashflow.publication.v1`，且 `selection_sha256` 与目标文件一致
- 目标权重非负、股票不重复，总和为 100%
- 明确传入至少一个飞书测试群 `--chat-id`

## 运行示例

```bash
uv run a-share-daily cashflow-delivery \
  --selection /path/to/selection.json \
  --source-date 20260904 \
  --signal-date 20260907 \
  --publication-receipt /path/to/publication-receipt.json \
  --chat-id oc_test_group \
  --receipt /path/to/cashflow-delivery-receipt.json
```

发送使用现有的 `lark-cli` bot 通道。幂等键由策略、signal date、目标群和产物 content hash 组成。重复运行时，系统会复用匹配的 delivery receipt，不会重复发送。

当前 adapter 不读取默认客户群，也不支持正式生产群配置。`--dry-run` 只生成状态为 `dry_run` 的回执，不代表消息已经送达。

## 定时影子桥接

`quant-intel-deploy` 中的 `scripts/run_cashflow_shadow.sh` 是部署桥接脚本，不包含策略逻辑。运行前需要在外部配置文件中提供明确路径和测试群 ID，例如：

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

可选的 `cashflow-feishu-shadow.timer` 在工作日 06:15 运行。只有明确设置 `CASHFLOW_SHADOW_ENABLE=1` 并执行 `setup_cron.sh --layer2` 时才会安装，默认不会启用。

如果设置了 `CASHFLOW_DATA_ROOT`，桥接脚本会先根据最新完整数据生成 PIT 审计回执，再调用编排器。审计未通过时，结果会保留并传给下游，但不会被当作可用特征。
