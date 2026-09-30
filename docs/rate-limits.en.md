# API rate-limit reference

[中文页面](rate-limits.md)

The values below are general troubleshooting references. Pipeline logic does not depend on them. Provider policies may change; verify current terms before planning live workloads.

| Provider | Free/entry-tier reference | Notes |
| --- | --- | --- |
| Alpha Vantage | 25 requests/day | Available for most datasets |
| Twelve Data | 8 credits/minute, 800/day | Most endpoints charge one credit per request |
| FMP | 250 requests/day | Paid tiers: 300–3,000/minute |
| Trading Economics | 1 request/second | Historical single-request limit: 10,000 rows |
| Finnhub | About 60 requests/minute | Respect `Retry-After` |
| Coinbase | About 10 requests/second | Advanced Trade REST |
| OKX | Public: 20/2 seconds; private: 10/2 seconds | — |
| SoSoValue | Tens of requests/minute | ETF requests are counted per API key |
| Alpaca | 200 requests/minute, 50,000/day | Market Data free tier |
| Cboe Put/Call | At most 1/minute | CSV retrieval |
| AAII | At most 1/day | Updated weekly |
| arXiv | At most 1/3 seconds | Send a compliant `User-Agent` |
| Stooq / Yahoo / yfinance | No official figure | Shared public sources; use conservative pacing |

Limits can change with provider policy.
