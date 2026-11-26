# 运行市场日报

[English page](run-daily-report.en.md)

## 你将得到什么

日报流程会依次完成数据抓取、主题评分和报告渲染。默认结果写入 `out/`，不会自动发送消息。

## 离线检查

只想确认命令是否可用时，运行：

```bash
API_KEYS='{}' uv run dm run --force-score
```

缺少可选数据源时，系统会记录降级状态。不同数据源的完整输出取决于本地配置和服务商权限。

## 分步运行

```bash
# 只抓取数据
API_KEYS='{}' uv run dm fetch

# 只计算主题评分
API_KEYS='{}' uv run dm score --force

# 只渲染报告
uv run dm digest
```

需要单独排查某一步时，使用分步命令更容易定位问题。

## 查看结果

常见输出包括：

- `out/etl_status.json`：数据抓取状态
- `out/scores.json`：主题评分
- `out/actions.json`：建议动作
- `out/index.html`：日报页面
- `out/digest_card.json`：消息卡片数据

完整字段说明见[产物契约](../contracts.md)。

## 使用真实数据

请把凭据放在环境变量或本地 Git 忽略文件中。不要把真实值写入仓库，也不要把生产输出复制到 public repository。

生产定时任务和消息目标由 `quant-intel-deploy` 管理。

## 美股日报跨资产补位

美股日报优先读取 Yahoo 的连续期货日线。布伦特、黄金、白银任一项缺失时，若 `API_KEYS_PATH` 指向的私有配置包含 `financial_modeling_prep`，才尝试 FMP 的 `BZUSD`、`GCUSD`、`SIUSD` 日线。FMP 必须返回报告日与前一有效交易日的正数收盘价，且报告日已过对应完成时点；两日涨跌幅在同一来源内计算。BTC 仍使用 Yahoo 的 CME 连续期货，SoSoValue 的 ETF 资金流不能替代币价。

另有独立的 `BTC/USD` 现货行情：优先用 FMP `BTCUSD` 的报告日及前一日 EOD；失败时依次采用已授权的 CoinGecko Pro `bitcoin/USD` 整点历史价格、Kraken `XBT/USD` 小时 K 线，后两者均取美东 16:00 的已完成截止点并与前一日同一截止点比较。三种来源都输出 `cross_asset.bitcoin_spot.*`，但在事实中标注实际来源与口径，绝不覆盖 `cross_asset.bitcoin.*` 的 CME 期货。CoinGecko 密钥配置在仓库外私有 `api_keys.json` 顶层的 `coingecko` 字段。若截止点缺失、重复、数值无效，或当前时间尚未到达截止点，就拒收该来源；全部不可用时保留缺项，不用旧值替代。CoinGecko Pro 请求被网络阻断时会自动尝试 Kraken，不能把 Kraken 数字标成 CoinGecko。

来源、代码和原始观测日随事实输出；FMP 提供的是其连续期货日线，不宣称等于交易所官方结算价。FMP 文档链接仅说明 API 来源，单条原始记录需要服务商授权访问。公开展示权以用户于 2026-09-26 的确认为依据，远程环境未取得授权文件。运营方仍需保存授权记录并核对具体许可范围。

## 美股休市日

指数和股票使用随包发布的 XNYS 日历文件
`daily_messenger.daily_report/data/equity_sessions_v1.json`，覆盖 2025–2027 年，
由 exchange-calendars 4.13.2 生成。报告日休市时，行情保留最近交易日的真实观测日
和该交易日涨跌，标记为 `quality=lagged`。`quotes` 与 `equities` 来源状态记录休市、
应有观测日、日历版本与来源。公开校验器独立核对这些信息；开市日仍拒绝较早行情。
美债、期货和连续交易的 BTC 各自使用对应契约。Alpaca 股票历史日线按 XNYS 实际
收盘时间及供应商等待时间判断完成，提前收盘日也使用实际时间。

Markdown 和文本按十进制四舍五入显示两位小数，负数采用绝对值进位，并消除负零。
JSON 证据保留原始精度。
