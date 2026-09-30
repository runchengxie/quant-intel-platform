# System architecture

[中文页面](architecture.zh-CN.md)

Market Intel contains independent pipelines for global-market data, A-share reports, and public web presentation. The pipelines share operational primitives and artifact contracts but keep their owners and failure boundaries explicit.

## Pipeline boundary

```text
source data
-> fetch and normalize
-> facts / events / research artifacts
-> schema, date, freshness, and hash validation
-> report and dashboard assembly
-> public pages or delivery receipt
```

`daily_messenger/` owns global-market ETL, topic scoring, reports, dashboards, and the `dm` CLI. `a_share_daily/` owns A-share reports, published strategy-artifact validation, charts, and delivery. `a_share_analysis/` consumes published research rather than implementing new research algorithms. `tushare_jobs/` is a lightweight report-side compatibility layer; authoritative A-share data belongs to `quant-market-data-platform`.

The `web/` application renders the public daily site, downloads, source displays, and `/docs/`. It consumes reviewed public snapshots and does not read production credentials.

## Cross-repository boundary

Research and strategy owners expose public CLIs or versioned artifacts. Market Intel may validate and render those artifacts, but it must not import owner business code or maintain a second implementation. Scheduler, delivery, credentials, and real runtime state belong to `quant-intel-deploy`.
