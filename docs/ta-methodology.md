# 技术分析方法论

本项目对 BTC/USDT 和 XAU/USD 分别实现了独立的技术分析报告生成。两者共享相同的指标体系，使用不同的数据源和计算引擎。

## 指标说明

### SMA（简单移动平均）

$$SMA_n = \frac{1}{n} \sum_{i=0}^{n-1} P_{t-i}$$

- BTC：SMA50（短均）和 SMA200（长均），使用 Pandas `rolling().mean()`
- XAU：窗口可配置，默认 SMA50/SMA200，使用纯 Python 滚动窗口实现
- 均线关系判定：SMA50 > SMA200 为金叉（偏多），反之为死叉（偏空）
- 结合价格与短均的位置进一步细分：价格在短均上方为偏多，下方则是回踩中或反弹观察

### 相对强弱指标（RSI）

$$RSI = 100 - \frac{100}{1 + RS}, \quad RS = \frac{\text{avg gain}}{\text{avg loss}}$$

- 默认周期：14
- BTC：使用 Wilder 平滑（EWM alpha = 1/14），通过 Pandas 实现
- XAU：标准 Wilder 平滑，纯 Python 实现。首窗口用简单平均，后续逐根递推
- 阈值：超买 ≥ 70，超卖 ≤ 30

### ATR（平均真实波幅）

$$TR = \max(H-L, |H-C_{prev}|, |L-C_{prev}|)$$
$$ATR_n = SMA(TR, n)$$

- 默认周期：14
- 单位：BTC 为 USDT，XAU 为美元
- XAU 的 volume 为 OANDA tick 计数，不等同于全市场成交量

### 枢轴点（Classic Floor Pivot）

基于前一交易日的 OHLC：

$$P = \frac{H + L + C}{3}$$
$$R_1 = 2P - L, \quad S_1 = 2P - H$$
$$R_2 = P + (H - L), \quad S_2 = P - (H - L)$$
$$R_3 = H + 2(P - L), \quad S_3 = L - 2(H - P)$$

- BTC：使用前一日 K 线
- XAU：使用前一个已完成的日线蜡烛（`complete=true`），切日时间为纽约 17:00

### 关键位检测（仅 XAU）

XAU 报告会检查当前价格是否接近关键位（S2, S1, P, R1, R2, 昨日高/低）。接近阈值默认为 0.1%（`near_pct=0.001`），命中时在报告交易提示中显示。

## BTC 模块

数据源：Binance 日度压缩包（历史）+ Binance/Kraken/Bitstamp REST API（增量）

抓取逻辑：

- `init-history`：一次性从 `data.binance.vision` 下载日度 zip 并合并为 Parquet
- `fetch`：增量刷新，按 Binance → Kraken → Bitstamp 优先级回退
- 存储格式：`out/btc/klines_{1m,1h,1d}.parquet`

报告生成：

- 日线必需，小时/分钟可选
- 配置控制：`include_intraday` 是否包含盘中快照，`intraday_granularities` 指定包含的粒度
- 分钟级报告额外计算 1m RSI14

## XAU 模块

数据源：OANDA Practice REST API（midpoint 报价）

关键配置（`config/ta_xau_*.yml`）：

```yaml
instrument: XAU_USD
alignmentTimezone: America/New_York
dailyAlignment: 17          # 纽约 17:00 切日
windows:
  sma_fast: 50
  sma_slow: 200
  rsi: 14
  atr: 14
thresholds:
  rsi_overbought: 70
  rsi_oversold: 30
  near_pct: 0.001           # 关键位接近判定阈值
```

三份配置对照：

| 配置 | 粒度 | 盘中快照 | 调度 |
|------|------|----------|------|
| `ta_xau_daily.yml` | D | 关闭 | 工作日 18:00 中国标准时间（CST） |
| `ta_xau_h1.yml` | D + H1 | 开启 | 每小时 :02 |
| `ta_xau_m5.yml` | D + M5 | 开启 | 每 5 分钟 :02 |

## 注意事项

- OANDA 为模拟账户数据源，volume 为 tick 计数，不适用于成交量分析
- 本地 DNS 可能将 `api-fxpractice.oanda.com` 解析到错误地址导致连接超时。所有 OANDA 工作流在 GitHub Actions 上运行正常，可在本地出问题时切换到远程触发
- 所有 TA 指标均为启发式参考，报告中的交易提示明确标注不构成建议
- BTC 日线不足 260 条时 CI 会自动回填近 400 天历史
- BTC/XAU 监控受 06:00–16:35 美国东部时间（ET） 守卫限制，非美股交易时段不触发