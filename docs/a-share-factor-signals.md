# A 股外部因子信号试验（历史记录）

> 本页仅保留迁移历史。因子面板、分钟特征、Hermite 和 walk-forward 已迁入
> 相关能力已经迁移到 research-workspace。market-intel 不再提供本页所述的产出入口或报告观察入口。

本页记录 `market-intel` 接入 A 股外部因子面板的当前状态。这里只用于工程试验和研究验证，不构成投资建议。

## 当前接入状态

`a-share-factor-core` 已支持读取外部 parquet factor panel，并在日频训练样本中按 `(date, symbol)` 拼接到特征矩阵。约定路径为：

```text
<external_factor_root>/<group>/<factor_name>.parquet
```

当前 `market-intel` 有一个精简分钟因子 smoke 工具：

```bash
uv run python -m a_share_analysis.factor_tools.minute_factor_smoke \
  --start-date 20260105 \
  --end-date 20260109 \
  --batch-size 20
```

它也可以按成交额流动性自动选股池，并支持日期区间、断点续跑、重试和 dry-run：

```bash
uv run python -m a_share_analysis.factor_tools.minute_factor_smoke \
  --universe liquidity \
  --universe-size 200 \
  --start-date 20251001 \
  --end-date 20260430 \
  --batch-size 20 \
  --sleep-seconds 0.5 \
  --resume
```

正式拉取前可以先看请求规模，不会触网调用 TuShare：

```bash
uv run python -m a_share_analysis.factor_tools.minute_factor_smoke \
  --universe liquidity \
  --universe-size 200 \
  --start-date 20251001 \
  --end-date 20260430 \
  --batch-size 20 \
  --dry-run
```

生产增量入口是 `scripts/refresh_a_share_factor_observation.sh YYYYMMDD`。该入口固定使用
一次解析出的 `token env + API URL`，并从 `market-data-platform` 的 Python 环境运行，
以便 Top200 和其他分钟消费者共用同一额度账本。安全约束如下：

- TuShare SDK 的 `retry_count` 固定为 `1`，`--retries` 只控制外层重试，因此每个物理请求都能单独记账。
- SDK 在不确定请求是否到达服务端时返回的通用 `OSError("ERROR.")` 只使用有上限的外层重试，每次物理尝试分别记为 request slot，重试耗尽后保守 checkpoint，下一调度日从已校验批次续跑。
- 每次请求前预留 `batch symbols × 241` 行，响应后提交实际行数，异常或中断保留为 `uncertain`。
- `--resume` 不以文件存在为成功条件。已有 parquet 必须匹配精确股票集合、精确交易日，且每股完整覆盖 `09:30–11:30` 和 `13:01–15:00` 共 241 个时间点。
- 新 raw parquet 先校验，再通过同目录临时文件原子替换，清单只记录完整完成的交易日和脱敏的凭证来源/endpoint。
- Top200 和 DailyWatch20 分钟下载固定使用本次解析出的单一凭证，模糊失败不会自动换令牌或重放。其他非分钟 TuShare 任务继续使用既有的 proxy-first/兜底 helper。

共享额度账本由以下环境变量控制，未设置时为 `off`，生产建议先用 `observe` 校准，再切到
`enforce`：

```env
MDP_TUSHARE_MINUTE_QUOTA_MODE=enforce
MDP_TUSHARE_MINUTE_QUOTA_DB=/path/to/minute_quota.sqlite3
MDP_TUSHARE_MINUTE_QUOTA_GATE=requests
MDP_TUSHARE_MINUTE_QUOTA_LIMIT_REQUESTS=10000
MDP_TUSHARE_MINUTE_QUOTA_BURST_LIMIT_REQUESTS=20000
MDP_TUSHARE_MINUTE_QUOTA_SAFETY_REQUESTS=500
MDP_TUSHARE_MINUTE_QUOTA_ALLOW_BURST=0
MDP_TUSHARE_MINUTE_QUOTA_LIMIT_ROWS=160000000
MDP_TUSHARE_MINUTE_QUOTA_SAFETY_ROWS=4000000
```

Top200 的 consumer 默认是 `top200_factor_observation`，DailyWatch20 默认是
`daily_watch20`。两者按实际使用的令牌指纹和 Asia/Shanghai 日期进入同一账本，凭证明文
不会写入 SQLite 或清单。版本化 systemd service 模板通过专用 lock 变量固定使用
request-first 门控：生产任务只使用完整的 10,000 次保底池及各自的 request hold，不进入
burst，21:15 后的历史 tail-filler 才可使用扣除 500 次探测余量后的浮动区间。行数仍保留为
吞吐遥测和任务软预算，不再近似服务商的请求次数硬限制。两个入口加载本地环境后仍显式传入
完整策略，避免 `.env.local` 意外覆盖，正常手工运行的默认值同样为 `enforce/requests`。

DailyWatch20 默认每批 33 只股票，即 `33 × 241 = 7,953` 行，接近单请求 8,000 行上限。
现有 Top200 历史输出根已经按 20 只/批落盘，因此生产增量继续固定为 20 只/批，在没有迁移到
新输出根前不得原地改为 33，否则旧日期的残余批次可能被离线 expand 混读。工具会拒绝与现有
清单不一致的批布局，并且原始完整性回执会拒绝同日期的额外批次。原始数据完整后会在
`$DATA_PLATFORM_ROOT/metadata/tushare/minute_quota/raw_completeness/YYYYMMDD/` 写原子回执。
Top200 回执写在 factor expand 与 walk-forward 之前，所以后续研究计算失败不会阻止调度器释放
原始下载预留，回执缺失则不得进入当晚 tail-filler。

默认输出在 `artifacts/a_share_minute_factor_smoke/factor_results/`，当前本机 smoke 产物为 20 只股票、5 个交易日、5 个分钟因子：

| group | factor | 说明 |
|-------|--------|------|
| `mf_volatility_32` | `realized_variance` | 日内 1 分钟对数收益平方和 |
| `mf_volatility_32` | `realized_skewness` | 日内收益偏度 |
| `mf_volatility_32` | `realized_kurtosis` | 日内收益峰度 |
| `mf_volatility_32` | `volume_volatility` | 分钟成交量变异系数 |
| `mf_volatility_32` | `price_elasticity` | 分钟高低价差相对成交额 |

这只是 `mf_volatility_32` 的 lite smoke 版，不含完整 32 因子。

已有 raw minute parquet 后，可以离线扩展成更完整的 32 因子，不再消耗 TuShare quota：

```bash
uv run python -m a_share_analysis.factor_tools.minute_factor_expand \
  --input-root artifacts/a_share_minute_factor_top200_202510_202604 \
  --group-name mf_volatility_32_full
```

该命令读取 `raw_minute/*.parquet`，输出到：

```text
artifacts/a_share_minute_factor_top200_202510_202604/factor_results/mf_volatility_32_full/
```

## 快速验证结果

截至 2026-07-06，本机 smoke panel 覆盖：

```text
5 trading days x 20 symbols x 5 factors
20260105 -> 20260109
```

用这 5 天因子对下一交易日 close-to-close 收益做截面 Rank IC，只能做接线检查，不能做统计结论。小样本读数如下：

| factor | days | mean Rank IC |
|--------|------|--------------|
| `price_elasticity` | 5 | -0.0734 |
| `realized_kurtosis` | 5 | 0.0078 |
| `realized_skewness` | 5 | -0.0343 |
| `realized_variance` | 5 | -0.1402 |
| `volume_volatility` | 5 | 0.0406 |

这些数值日间波动很大，样本太短，不能据此判断因子有效或无效。

当前也新增了一个 baseline vs `baseline + minute factors` 的小型实验脚本：

```bash
uv run python -m a_share_analysis.factor_tools.incremental_experiment \
  --train-start 2024-01-01 \
  --train-end 2025-12-31 \
  --test-start 2026-01-01 \
  --test-end 2026-04-30 \
  --universe-size 200 \
  --top-k 20
```

脚本会生成两个日频组合序列，并在
`artifacts/a_share_factor_incremental_experiment/summary.json` 输出：

| 指标 | 含义 |
|------|------|
| `mean_rank_ic` | 测试期日均截面 Rank IC |
| `topk_cum_return` | TopK 组合测试期累计收益 |
| `topk_max_drawdown` | TopK 组合最大回撤 |
| `mean_turnover` | TopK 日均换手 |
| `mean_stability` | TopK 日均持仓重合度 |

本机用已有 5 天 smoke panel 做了一次链路验收：20 只股票，2 个训练日，
3 个测试日，Top5。结果只能说明脚本能完整产出指标，样本太短，不用于判断因子优劣。

实验脚本也支持从清单复用同一批股票，并直接读取某个 factor group：

```bash
uv run python -m a_share_analysis.factor_tools.incremental_experiment \
  --symbols-from-manifest artifacts/a_share_minute_factor_top200_202510_202604/minute_factor_manifest.json \
  --train-start 20251009 \
  --train-end 20260309 \
  --test-start 20260310 \
  --test-end 20260430 \
  --top-k 20 \
  --factor-root artifacts/a_share_minute_factor_top200_202510_202604/factor_results \
  --external-factor-group mf_volatility_32_full
```

## Top200 扩展结果

截至 2026-07-06，本机已有一份 top200 分钟数据和扩展因子：

| 数据 | 数值 |
|------|------|
| raw minute 范围 | `20251009` -> `20260430` |
| 交易日 / 股票 | `137 x 200` |
| raw minute 请求 | `1370/1370` |
| raw+factor 目录大小 | 约 `177M` |
| full group | `mf_volatility_32_full` |
| full factor 数 | `32` |

同一股票池、前 100 个交易日训练、后 37 个交易日测试，Top20 读数：

| 模型 | mean Rank IC | Top20 累计收益 | max drawdown | 换手 | 稳定性 |
|------|--------------|----------------|--------------|------|--------|
| baseline daily | `0.0081` | `12.08%` | `-9.94%` | `0.374` | `0.626` |
| baseline + lite5 | `0.0065` | `8.98%` | `-10.41%` | `0.479` | `0.521` |
| baseline + full32 | `0.0401` | `14.54%` | `-11.29%` | `0.654` | `0.346` |
| baseline + volume_activity5 | `0.0341` | `15.81%` | `-9.33%` | `0.499` | `0.501` |

`volume_activity5` 是当前更值得继续跟踪的候选组合：

```text
volume_volatility
log_volume_volatility
diff_abs_mean_volume
peak_count_1std
peak_count_2std
```

它比 full32 更稀疏、更可解释，Top20 收益和回撤更好，但换手仍明显高于 baseline。
下一步应优先做 walk-forward 和换手惩罚/持仓平滑，暂缓引入 Hermite。

## Walk-forward 与持仓平滑

`volume_activity5` 已有一个滚动训练、交易成本和持仓策略 sweep 工具：

> 本节保留的是早期 close-to-close 候选筛选读数，其收益口径已被下方盘后信号严格时点复核取代。

```bash
uv run python -m a_share_analysis.factor_tools.walk_forward \
  --train-window 60 \
  --test-window 10 \
  --cost-bps 20 \
  --turnover-caps 0.30,0.50 \
  --score-smoothing-values 0.35,0.50 \
  --output-root artifacts/a_share_factor_walk_forward_volume_activity5_costed_60_10
```

脚本会同时评估 baseline 和 `volume_activity5`。`topk_ret/topk_nav` 保留毛收益，
`topk_net_ret/topk_net_nav` 按 `cost_bps` 扣除换手成本。当前成本口径是：
每 100% 持仓替换扣 `cost_bps / 10000`，第一天建仓不扣成本。

默认 sweep 包括：

```text
daily
daily_hold_bonus_0_02 / 0_05 / 0_10
rebalance_2d / 3d / 5d
rebalance_2d / 3d / 5d + hold_bonus_0_05
daily / rebalance_3d + turnover_cap_0_30 / 0_50
daily / rebalance_3d + score_smoothing_0_35 / 0_50
score_smoothing + turnover_cap 组合
```

20bps 成本后的主要读数：

| 口径 | 模型 / 策略 | Rank IC | 毛收益 | 净收益 | 净 max DD | 换手 |
|------|-------------|---------|--------|--------|-----------|------|
| fixed 100/37 | baseline daily | `0.0081` | `12.08%` | `9.11%` | `-10.48%` | `0.374` |
| fixed 100/37 | volume daily + hold bonus 0.05 + cap 0.50 | `0.0341` | `18.24%` | `15.14%` | `-9.14%` | `0.369` |
| fixed 100/37 | volume daily + hold bonus 0.05 + cap 0.30 | `0.0341` | `14.93%` | `12.57%` | `-10.23%` | `0.289` |
| walk 100/10 | baseline daily | `0.0024` | `12.53%` | `8.87%` | `-10.48%` | `0.460` |
| walk 100/10 | volume daily + hold bonus 0.05 | `0.0434` | `18.69%` | `14.80%` | `-9.14%` | `0.465` |
| walk 100/10 | volume rebalance 3d + cap 0.30 | `0.0434` | `14.56%` | `13.74%` | `-11.67%` | `0.100` |
| walk 80/10 | baseline daily | `0.0042` | `15.30%` | `10.04%` | `-14.20%` | `0.418` |
| walk 80/10 | volume rebalance 3d + cap 0.50 | `0.0307` | `28.33%` | `26.11%` | `-12.63%` | `0.156` |
| walk 80/10 | volume rebalance 3d + smoothing 0.50 + cap 0.30 | `0.0307` | `23.16%` | `21.85%` | `-14.31%` | `0.096` |
| walk 60/10 | baseline daily | `-0.0106` | `7.77%` | `0.74%` | `-20.03%` | `0.444` |
| walk 60/10 | volume rebalance 3d + smoothing 0.50 + cap 0.30 | `0.0085` | `23.13%` | `21.33%` | `-18.65%` | `0.097` |
| walk 60/10 | volume daily | `0.0085` | `11.03%` | `2.46%` | `-20.36%` | `0.529` |

阶段结论：

1. `volume_activity5` 的 Rank IC 改善比较一致，说明它在单次 100/37 切分之外也能稳定复现。
2. 交易成本会显著惩罚 daily 高换手方案，`volume daily` 在 `60/10` 下毛收益 `11.03%`，
   净收益只剩 `2.46%`。
3. 当前最值得继续跟踪的是两类组合：
   `daily_hold_bonus_0.05 + turnover_cap_0.50` 和
   `rebalance_3d + turnover_cap/smoothing`。前者在短后验窗口更强，
   后者在滚动窗口中换手更低、净收益更稳。
4. 旧口径下，`walk 80/10` 的 `volume rebalance_3d_turnover_cap_0.50` 表现最强：
   净收益 `26.11%`，换手 `0.156`。
5. 进入下一阶段前，应扩大历史、提高股票池规模，并用更严格的成本/冲击模型复核，
   Hermite 已可生成 meta panel，但仍需在同一 walk-forward 框架下验证降权/稳定性增益。

### 盘后信号严格时点复核

上面的早期 walk-forward 使用 `close(T+1) / close(T) - 1`。分钟因子要等 T 日收盘后
才能完整生成，因此该标签包含无法在实盘获得的 `close(T) -> open(T+1)` 隔夜区间。
旧收益只能用于候选筛选，不能作为可交易 Alpha 证据。

严格审计改为：

```bash
uv run python -m a_share_analysis.factor_tools.volume_oos_audit
```

- 信号在 T 日完整分钟数据落盘后生成，标签为 `open(T+2) / open(T+1) - 1`。
- 每个滚动 fold purge 1 个信号日，避免训练末端标签跨入测试期。
- 固定使用 `rebalance_3d_turnover_cap_0.30`，不在新测试结果上挑持仓政策。
- 同时报告 10/20/30/50 bps，涨停买入和跌停卖出只统计真实目标变更，不事后替补。
- 收益表示假设目标均能成交时的上界，不模拟涨跌停卡单下的完整执行，发生阻断即禁止晋级。
- `volume_activity5` 这五个因子曾在重叠历史样本上预筛选，本轮并非 untouched factor holdout，
  显著 IC 增量仍存在 multiple-selection bias，必须在新增长的冻结样本上复核。
- 候选池只按 T 日可见条件形成，绝不因 `T+2` 标签缺失而提前删股票，测试时先对完整候选池
  评分并冻结选择。任何 Top20 标签或冻结持仓行缺失，整日收益及整段组合推断均 fail-closed。
- `open(T+1) -> open(T+2)` 使用全市场统一的 2 个交易日成熟期，数据截止日前最后两个信号日
  在评分前按日历整体排除，不按个股未来结果过滤。成熟区间内仍执行上述个股级门禁。
- 每只股票都按清单的全市场交易日精确查找 T+1/T+2，不再对个股日线直接 `shift`。
  若停牌期间整行缺失，标签和交易状态保持未知，不允许跳到复牌日代替目标交易日。

截至 2026-07-10 的本机数据共有 184 个信号时候选日，2026-07-09 和 2026-07-10
按标签成熟日历整体排除。精确日历映射还识别出成熟区间内 15 个日期存在至少一个个股未来行
缺失。主口径为 80 日训练、10 日测试，正式样本外（OOS） 为 2026-02-03 至 2026-07-08，
共 101 日，其中 7 日的全市场主动收益不可用，Top20 标签本身 101 日完整。30 bps 下读数为：

| 指标 | baseline | baseline + volume_activity5 | 配对增量 |
|------|---------:|----------------------------:|---------:|
| mean Rank IC | `0.0264` | `0.0474` | `+0.0210` |
| Rank IC HAC t | `1.47` | `2.81` | `3.69` |
| Top20 目标净日收益 | `0.2295%` | `0.2957%` | `+0.0661%` |
| 对应 HAC t | `0.82` | `1.00` | `0.69` |
| 平均目标换手 | `0.108` | `0.108` | - |

60/80/100 日三个训练窗的 IC 配对增量均为正，HAC t 分别为 `2.88/3.69/3.66`，
但扣费收益配对增量 HAC t 只有 `0.34/0.69/不可用`。100 日训练窗有 2 个 Top20
标签缺失，整段收益推断按门禁作废，不能用剩余 79 日替代正式结论。
主 80 窗 94 个标签完整日的净主动收益仅作描述：volume 版本均值为 `0.2178%`，
HAC t 为 `1.13`，由于缺失日并非随机留出的样本，不能把它当作全段主动收益证据。

最近 20/40 个 OOS 日只是同一主窗口尾部的稳定性诊断，并非独立 holdout：

| 尾部窗口 | IC 配对增量 | IC 增量 HAC t | 净收益配对增量 | 净增量 HAC t |
|---------:|------------:|----------------:|----------------:|-------------:|
| 20 日 | `-0.0039` | `-0.42` | `+0.3964%/日` | `2.18` |
| 40 日 | `+0.0097` | `1.27` | `+0.1311%/日` | `0.70` |

20 日里收益增量较强但 IC 增量转负，40 日里 IC 恢复为正但两类增量都不显著，短窗方向
并不稳定，且没有承担独立留样或多重检验职责，不能据其中一个 t 值晋级。
主口径还观察到 6 次涨停买入阻断和 6 次跌停卖出阻断，静态 Top200 同样并非
point-in-time universe。完整证据在
`artifacts/a_share_minute_volume_oos_audit/summary.json`，自动晋级状态为 `research_only`。
晋级失败原因还明确包含 `untouched_factor_holdout=false`，不能把当前 HAC t 当成独立发现的
显著性检验。证据中的 `complete_oos_portfolio_returns`、`complete_paired_oos_returns` 与
`complete_trade_status` 通过，但 `complete_oos_active_returns=false`，这正是全市场候选标签
缺行时的 fail-closed 结果。后续任何 Top20 标签、冻结持仓行或交易状态缺失，还会进一步
使组合或配对收益门禁失败。

因此，当前结论收紧为：`volume_activity5` 是值得扩展历史和股票池继续验证的候选特征，
但尚不能称为可交易 Alpha，也不应按旧的 close-to-close 收益直接进入生产组合。

## Hermite Meta 的定位

`hermite_factor_meta` 是对已有 factor panel 做变换得到的元特征算子，不直接由日线或分钟线生成。它读取已有 factor panel，对每个股票的因子时间序列做滚动 z-score，再计算 Hermite `h3/h4` 能量：

| 输出 | 含义 |
|------|------|
| `*_ts_h3_60` | 60 日滚动三阶非高斯形态 |
| `*_ts_h4_60` | 60 日滚动四阶尾部/峰度形态 |
| `*_ts_closeness_60` | 因子状态接近高斯稳定区的程度 |
| `*_energy_compression_20_60` | 短窗和长窗非高斯能量的压缩/扩张 |

它至少需要足够长的日频因子历史。按原始配置，60 日窗口需要约 36 个有效观测才开始有值，真正用于训练时建议至少 1-2 年日频 factor panel。

截至 2026-07-06，本机 `top200` 分钟因子 panel 已扩展到 `20251009 -> 20260706`，共 `180 x 200`，并已生成 `hermite_factor_meta` 的 20 个 meta panel。当前处理分两层：

- 晨报/晚报底部的因子技术观察仍只展示 walk-forward 研究读数和 Hermite 生成状态。
- 每日热点候选预览会在 hotsector 原始候选排序上，尝试读取 `volume_activity5` 与 Hermite closeness 面板，作为小权重辅助排序和标签展示，缺少覆盖时按热点候选原排序安全降级。

这表示 Hermite 已进入候选池质量观察 / 稳定性辅助链路，但仍不作为独立 alpha 直接替代热点排序。

## 推荐验证路径

1. 保持全市场日线数据作为基础宇宙和标签。
2. 先对 top 200 或 top 500 流动性股票下载 2024-2026 的 1 分钟数据。
3. 生成完整或扩展版 `mf_volatility_32` panel，先只接 5-10 个低相关、可解释的分钟因子，并做 winsor/zscore。
4. 用相同训练/测试切分比较：
   - daily baseline，
   - baseline + minute factor，
   - baseline + minute factor + Hermite meta。
5. 主要看 test Rank IC、TopK 收益、最大回撤和换手，不单看单日 IC。

当前优先级是先证明分钟波动/流动性因子有没有增益。Hermite 已具备二阶段数据基础，
下一步应比较：

- baseline，
- baseline + minute factor，
- baseline + minute factor + Hermite meta / 降权规则。

它只判断该因子最近是否进入不稳定状态、尾部/偏态是否突然变强，以及当前信号是否应该降权，不替代原始分钟因子。当前产品口径应表述为：热点追踪为主，交易相关特征为辅，
候选关注股票池仅供研究参考。
