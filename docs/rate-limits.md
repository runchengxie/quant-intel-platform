# API 限频参考

以下为通用参考值，流水线不基于限制做逻辑判断，仅供排障。

| 提供商 | 免费/入门限额 | 备注 |
|--------|-------------|------|
| Alpha Vantage | 25 次/天 | 多数数据集可用 |
| Twelve Data | 8 credits/分钟，800/天 | 多数端点 1 请求 = 1 credit |
| FMP | 250 次/天 | 付费档 300–3000/分钟 |
| Trading Economics | 1 请求/秒 | 历史单次上限 10000 行 |
| Finnhub | ~60 次/分钟 | 需尊重 Retry-After |
| Coinbase | ~10 次/秒 | Advanced Trade REST |
| OKX | 公共 20 次/2 秒 | 私有 10 次/2 秒 |
| SoSoValue | 几十次/分钟 | ETF 数据按 API Key 计数 |
| Alpaca | 200 次/分钟，50000/天 | Market Data 免费档 |
| Cboe Put/Call | ≤1 次/分钟 | CSV 拉取 |
| AAII | ≤1 次/日 | 每周更新 |
| arXiv | ≤1 次/3 秒 | 遵守 User-Agent |
| Stooq / Yahoo / yfinance | 无官方数字 | 共享公共源，自觉限速 |

限额可能随供应商策略调整。