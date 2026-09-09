# v0.1.5 clean parity replay

日期：2026-09-09  Asia/Shanghai  
状态：`clean_replay`，计入 parity 观察，不计入五个交易日完成门禁

## 输入与运行身份

- old artifact：当前 canonical production report root 中的 `20260908` morning manifest；
- new framework：public `quant-intel-platform v0.1.5`，commit
  `6c3d8f174e0b2a861d9ac0aec7773dd7dbd14549`；
- source date：`20260908`；signal date：`20260909`；
- DailyWatch20：versioned run
  `strategy_outputs/watchlist20/runs/20260909_20260909T010801Z_fd59c76e`；
- cross-market：从 old manifest 冻结为 exact-date snapshot，未让 replay 读取 live
  yfinance/FRED fallback；
- production configuration：启用 `A_SHARE_ENABLE_TUSHARE_PREMIUM=1`；
- delivery：只生成 artifact，未发送消息。

## 运行结果

v0.1.5 historical replay：

- exit status：`0`；
- core freshness：`daily`、`daily_basic`、`adj_factor`、`limit_status` 均为
  `20260908`；
- DailyWatch20：`source=20260908`、`signal=20260909`、5 个 topic；
- charts：topic、moneyflow、sentiment、dashboard、weekly chart/text、US overnight
  均成功；
- cross-market source：`data-snapshots`，无 warning、无 error。

Comparator 运行：

```bash
uv run python -m tests.parity.run_parity \
  --source-date 20260908 \
  --signal-date 20260909 \
  --old-root "$OLD_ROOT" \
  --new-root "$NEW_ROOT" \
  --output-root "$RESULT_ROOT" \
  --path-field paths \
  --path-field cross_market \
  --ignore-field _freshness_warnings \
  --ignore-field _source \
  --ignore-field as_of_date \
  --ignore-field stale_days \
  --ignore-field instructions \
  --ignore-field cross_market_summary
```

结果：

```text
unexplained_differences=false
missing_from_old=[]
missing_from_new=[]
differences={}
```

## 归一化边界

仅归一化运行环境元数据：绝对路径、snapshot source 标记、宏观 freshness 元数据、
instructions 和 derived summary path。没有忽略业务数值、核心 freshness 日期、topic
内容、chart 成功状态或 artifact 集合。

冻结输入中的 TNX `as_of_date` 被设置为目标日以阻止 loader 因旧 manifest 的历史 freshness
warning fallback 到 live provider；TNX 的数值仍来自 old manifest，日期/`stale_days` 作为
已声明元数据字段忽略。

## 结论

这是第一条使用生产配置、完整增强数据和 versioned DailyWatch20 artifact 的 v0.1.5
clean replay。它证明当前观察日的行为差异已经可以由声明的环境元数据归一化解释，但不
等于五日 parity gate、失败恢复周期、canary 或 production cutover 已通过。
