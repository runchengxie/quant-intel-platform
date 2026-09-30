[中文页面](data-fetch-architecture.md)

# Cross-market data-fetch architecture

## Three-layer fallback design

The reporting pipeline uses three progressively later opportunities to obtain overseas-market data:

```text
Layer 1: GitHub Actions       05:00     cross-market.yml → data-snapshots/
Layer 2: Local scheduler      06:00/07:00  check and fetch missing data
Layer 3: Report pipeline      07:00     Windows morning_pipeline.ps1 → preview + report → delivery
```

### Layer 1: GitHub Actions snapshot

Workflow: `.github/workflows/cross-market.yml`  
Schedule: weekdays at 05:00 China Standard Time (CST), or 21:00 UTC on the previous day.

The workflow uses yfinance on a GitHub runner to fetch US equities, Japanese and Korean semiconductor stocks, commodities, macro indicators, and sentiment data. It writes snapshots under `data-snapshots/` and commits them to the repository.

Coverage includes:

- US Magnificent Seven and semiconductor stocks: NVDA, AMD, AVGO, TSLA, AAPL, MSFT, GOOGL, AMZN, META
- Japanese and Korean semiconductor names, including Tokyo Electron, Advantest, Samsung, and SK Hynix
- Benchmarks: SPY, QQQ, SMH, `^N225`, `^KS11`
- Commodities: `GC=F`, SLV, GLD
- Macro series: DXY, VIX via FRED, and the 10-year yield via FRED
- Sentiment: AAII and CBOE/VIX

Outputs:

- `data-snapshots/cross-market/YYYY-MM-DD.json`
- `data-snapshots/latest/cross_market_snapshot.json`
- `data-snapshots/latest/cross_market_snapshot.md`

### Layer 2: local validation and fallback fetch

Linux uses `scripts/local_fetch_cross_market.sh` on weekdays at 06:00 CST. Its systemd user units are `~/.config/systemd/user/local-fetch-cross-market.{service,timer}`. Windows uses `scripts/windows/morning_pipeline.ps1` at 07:00 CST.

Linux installation renders the `scripts/systemd/*.service` templates with `scripts/setup_cron.sh --layer2`. Windows installation registers Task Scheduler tasks with `scripts/windows/install_scheduled_tasks.ps1 -Force`.

The fallback flow:

1. Pull the latest Layer 1 snapshot with `git pull`.
2. Run `fallback_fetch.py`.
3. Reuse a matching snapshot from `data-snapshots/` and mark its source as `_source: data-snapshots`.
4. If the snapshot is missing or more than two days old, fetch current data locally through yfinance. The fetch can use the mihomo proxy at `127.0.0.1:7890`.

Log: `~/.hermes/logs/local_fetch_cross_market.log`.

### Layer 3: final report-time fallback

The Windows entry point is `Market Intel Morning`, scheduled for 07:00 CST on weekdays. It runs `scripts/windows/morning_pipeline.ps1`, then the hot-sector stock preview, `a-share-daily morning`, and `a-share-daily morning-report`.

Inside `a-share-daily morning`, `cross_market.py run()` first checks the Layer 1/2 snapshot and triggers a live fetch if it is unavailable. If data remains unavailable, the report marks missing items and continues delivery.

The Hermes daily schedule is paused by default. It is a manual resend or temporary takeover path and should not run alongside Windows `Market Intel Morning`.

## Asian-market data fallback

The Korean pre-market signal has an optional provider chain and does not require a KRX Open API key:

```text
FinanceDataReader (no key)
        ↓ failure or unavailable
pykrx (no key)
        ↓ failure or unavailable
yfinance (existing fallback)
```

The output fields are `korea_preopen` and `korea_overnight`; both retain `source` and `degraded`. Without a key, the chain supplies daily-bar proxies, not live NXT/KRX intraday data or KOSPI 200 overnight-session data. Reports label these as daily proxies, not intraday data. A future minute-data provider can supply the same quote structure to `compute_korea_signal` without changing the report contract.

The morning signal uses Korean semiconductor returns relative to `^KS11` as a directional residual. The after-hours/overnight signal is an early warning for the next A-share session. These are informational signals, not trading instructions.

## Evening data path

The evening pipeline follows the same layered pattern:

```text
Layer 1: GitHub Actions tushare-daily       09:30  → lightweight TuShare snapshot
Layer 2: Local scheduler                   17:30–18:40  → refresh TuShare and Japan/Korea data
Layer 3: Windows evening pipeline          19:00  → charts and text → delivery
```

`evening_pipeline.sh` refreshes data and generates charts before delivery. When premium TuShare access is disabled, hotspot-theme and `moneyflow_ths` charts are skipped. With `A_SHARE_ENABLE_TUSHARE_PREMIUM=1`, if today's hotspot or `moneyflow_ths` data is unavailable, the workflow creates a Chinese placeholder chart so that a chart from the previous trading day is not sent. Delivery prefers chart paths in `evening_manifest.json` and sends only artifacts from the current run.

Web charts use a separate offline-candidate boundary. The morning pipeline records the limited point set used for six charts in private `charts.public_points`. `a-share-daily chart-candidate` exports `market_intel.a_share_charts.v1` JSON for an explicit date and morning/evening identity. It does not refresh data, read PNGs, send Feishu messages, or write directly to Pages. Older cross-market snapshots without per-symbol `as_of_date` and source URLs leave US-equity points absent; newer snapshots record both fields when downloaded. Evening may reuse same-day chart data, but must use `evening` for `report_id` and candidate filenames to avoid overwriting the morning candidate.

## Daily timeline

Times below are China Standard Time (CST, UTC+8), except where noted.

| Time | Event |
| --- | --- |
| 05:00 | Layer 1 `cross-market.yml` workflow |
| 06:00 | Linux Layer 2 systemd timer |
| 07:00 | Windows `Market Intel Morning`; stock preview and morning report |
| 08:00–15:00 | Asian trading sessions and A-share close |
| 17:30 | Layer 2 A-share and Asia core-data refresh |
| 18:00 | Layer 2 current contract and universe publication |
| 18:20 / 18:40 | Two enhancement-data fetch attempts before the evening report |
| 19:00 | Windows/Hermes Market Intel Evening |
| 19:20 / 20:30 | Enhancement-data backfill for the next morning report and freshness recovery |
| 21:00 | Optional minute-factor / Hermite demo batch |

US market times vary with daylight saving time; the source schedule places the open at approximately 21:30 CST.

## Market coverage

### Indexes

- Nikkei 225 (`^N225`) and KOSPI (`^KS11`) are fetched through yfinance and included in `BENCHMARK_SYMBOLS`.

### Semiconductor names used as cross-market leading indicators

- Japan: 8035.T (Tokyo Electron), 6857.T (Advantest), 6146.T (Disco), 6723.T (Renesas), 6920.T (Lasertec)
- Korea: 005930.KS (Samsung Electronics), 000660.KS (SK Hynix), 042700.KS (Hanmi Semiconductor)

### Market news

`MarketNewsSpec` covers `us`, `jp`, `hk`, `kr`, `cn`, and `gold`. Korea uses the Asia/Seoul time zone and a 15:30 close.

## Failure fallback

| Scenario | Layer 1 | Layer 2 | Layer 3 | Outcome |
| --- | --- | --- | --- | --- |
| Normal | Succeeds | Reuses snapshot | Reuses snapshot | Complete data |
| GitHub Actions fails | Fails | Fetches with yfinance | Reuses Layer 2 | Complete data |
| GitHub Actions and local fetch fail | Fails | Fails | Fetches with yfinance | Complete, delayed data |
| All attempts fail | Fails | Fails | Fails | Degraded report with missing data marked |

## Related files

| File | Purpose |
| --- | --- |
| `.github/workflows/cross-market.yml` | Layer 1 GitHub Actions workflow |
| `scripts/local_fetch_cross_market.sh` | Linux Layer 2 script |
| `scripts/windows/morning_pipeline.ps1` | Windows morning entry point, including the hot-sector preview |
| `scripts/windows/evening_pipeline.ps1` | Windows evening entry point, including market-data-platform refresh |
| `scripts/windows/install_scheduled_tasks.ps1` | Registers Windows Task Scheduler tasks |
| `scripts/windows/preflight.ps1` | Preflight checks for Windows production tasks |
| `scripts/windows/test_scheduled_tasks.ps1` | Isolated one-off Windows smoke task |
| `scripts/systemd/local-fetch-cross-market.service` | Linux Layer 2 service template rendered by `setup_cron.sh` |
| `src/a_share_daily/cross_market.py` | Core fetch logic and snapshot fallback |
| `src/a_share_daily/fallback_fetch.py` | Snapshot-first fallback shared by Layers 2 and 3 |
| `src/a_share_daily/global_leadlag.py` | Global leading-asset mapping and benchmarks |
| `src/daily_messenger/common/market_news.py` | Market trading-session specifications |
| `scripts/morning_pipeline.sh` | Layer 3 morning entry point |
| `scripts/evening_pipeline.sh` | Evening entry point |

## Maintenance

### Add a market

1. Add a `MarketNewsSpec` in `market_news.py`.
2. Add relevant assets or indexes in `global_leadlag.py`.
3. Update summary generation in `cross-market.yml`.
4. Update this page.

See [Daily schedule](daily-schedule.md) for the full intraday schedule.

### Change the Layer 2 schedule

```bash
systemctl --user edit local-fetch-cross-market.timer
# Edit OnCalendar, then:
systemctl --user daemon-reload
systemctl --user restart local-fetch-cross-market.timer
```

### Run manually

```bash
# Run Layer 2
systemctl --user start local-fetch-cross-market.service

# View logs
journalctl --user -u local-fetch-cross-market.service -n 50

# Run Layer 3 manually
hermes cronjob run fc559b72e51c
```
