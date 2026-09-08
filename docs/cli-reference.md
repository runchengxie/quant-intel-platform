# CLI 参考

本文件由 `project_tools/update_cli_help.py` 自动生成，只覆盖 `dm` 命令。本地 pre-push 质量门会校验本文件是否与 `dm --help` 的输出保持一致。`marketops` 与 `a-share-daily` 的子命令结构请以各自 `--help` 为准（例如 `marketops tushare --help`、`a-share-daily --help`）。

<!-- cli-help:start -->
```text
$ dm --help
usage: dm [-h]
          {run,fetch,score,digest,dashboard,state-panel,btc,style-replica} ...

Daily Messenger CLI

positional arguments:
  {run,fetch,score,digest,dashboard,state-panel,btc,style-replica}
    run                 Run ETL, scoring, and digest sequentially
    fetch               Run ETL only
    score               Run scoring only
    digest              Render digest only
    dashboard           Build static market intelligence dashboard
    state-panel         Build dashboard market-state panel from public sources
    btc                 BTC monitoring helpers
    style-replica       Generate the internal-only legacy StyleReplica report

options:
  -h, --help            show this help message and exit

$ dm run --help
usage: dm run [-h] [--date DATE] [--force-fetch] [--force-score] [--degraded]
              [--strict] [--disable-throttle]

options:
  -h, --help          show this help message and exit
  --date DATE         Override trading day (YYYY-MM-DD)
  --force-fetch       Force refresh ETL step
  --force-score       Force recompute scoring step
  --degraded          Render digest in degraded mode
  --strict            Enable STRICT mode during scoring
  --disable-throttle  Disable network throttling helpers

$ dm fetch --help
usage: dm fetch [-h] [--date DATE] [--force] [--disable-throttle]

options:
  -h, --help          show this help message and exit
  --date DATE         Override trading day (YYYY-MM-DD)
  --force             Force refresh ETL step
  --disable-throttle  Disable network throttling helpers

$ dm score --help
usage: dm score [-h] [--date DATE] [--force] [--strict]

options:
  -h, --help   show this help message and exit
  --date DATE  Override trading day (YYYY-MM-DD)
  --force      Force recompute scoring
  --strict     Enable STRICT mode

$ dm digest --help
usage: dm digest [-h] [--date DATE] [--degraded]

options:
  -h, --help   show this help message and exit
  --date DATE  Override trading day (YYYY-MM-DD)
  --degraded   Render in degraded mode

$ dm dashboard --help
usage: dm dashboard [-h] [--out OUT] [--state-panel STATE_PANEL]
                    [--snapshot-dir SNAPSHOT_DIR] [--no-payload-json]

options:
  -h, --help            show this help message and exit
  --out OUT             Output HTML path (default: out/web_dashboard.html)
  --state-panel STATE_PANEL
                        Optional CSV with market-state proxy columns
  --snapshot-dir SNAPSHOT_DIR
                        Directory containing latest snapshot JSON files
  --no-payload-json     Do not write web_dashboard_payload.json next to the
                        HTML file

$ dm state-panel --help
usage: dm state-panel [-h] [--out OUT] [--period PERIOD] [--start START]
                      [--include-breadth] [--breadth-mode {sample,full}]
                      [--timeout TIMEOUT] [--min-rows MIN_ROWS]

options:
  -h, --help            show this help message and exit
  --out OUT             Output CSV path (default: out/market_state_panel.csv)
  --period PERIOD       yfinance lookback period when --start is not set
                        (default: 10y)
  --start START         Start date for historical sources (YYYY-MM-DD)
  --include-breadth     Also fit SPX/NDX 20/50/200D breadth
  --breadth-mode {sample,full}
                        Use core sample constituents or full current public
                        constituents (default: sample)
  --timeout TIMEOUT     HTTP timeout in seconds (default: 20)
  --min-rows MIN_ROWS   Fail when fewer effective rows are produced (default:
                        30)

$ dm btc --help
usage: dm btc [-h] {init-history,fetch,report} ...

positional arguments:
  {init-history,fetch,report}
    init-history        一次性下载 Binance 日度压缩包并合并为 Parquet
    fetch               增量刷新 Binance/Kraken/Bitstamp K 线并写入 Parquet
    report              生成 BTC Markdown 日报

options:
  -h, --help            show this help message and exit

$ dm style-replica --help
usage: dm style-replica [-h] [--positions POSITIONS] [--date DATE]
                        [--user-id USER_ID] [--dry-run] [--internal-only]

options:
  -h, --help            show this help message and exit
  --positions POSITIONS
                        Path to positions CSV
  --date DATE           Signal date YYYYMMDD (default: today)
  --user-id USER_ID     Internal Feishu open_id; must match
                        STYLE_REPLICA_INTERNAL_FEISHU_USER_ID
  --dry-run             Print instead of sending
  --internal-only       Acknowledge that this legacy report may only go to the
                        internal allowlist
```
<!-- cli-help:end -->