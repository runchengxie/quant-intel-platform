# System architecture

[Chinese version](architecture.zh-CN.md)

quant-intel-platform contains independent pipelines for global-market data and A-share reports. The pipelines share operational primitives and artifact contracts but keep their owners and failure boundaries explicit.

## Pipeline boundary

```text
source data
-> fetch and normalize
-> facts / events / research artifacts
-> schema, date, freshness, and hash validation
-> report assembly
-> public snapshot / delivery receipt
```

`daily_messenger/` owns global-market ETL, topic scoring, reports, dashboards, and the `dm` CLI. `a_share_daily/` owns A-share reports, published strategy-artifact validation, charts, and delivery. `a_share_analysis/` consumes published research rather than implementing new research algorithms. `tushare_jobs/` is a lightweight report-side compatibility layer; authoritative A-share data belongs to `quant-market-data-platform`.

The platform produces validated public report snapshots through `market_intel_publication`. The separate `quant-intel-pages` repository renders and hosts the daily site. MkDocs publishes platform documentation at `/docs/`; the platform site's root redirects to Pages for compatibility.

## Cross-repository boundary

Research and strategy owners expose public CLIs or versioned artifacts. quant-intel-platform may validate and render those artifacts, but it must not import owner business code or maintain a second implementation. Scheduler, delivery, credentials, and real runtime state belong to `quant-intel-deploy`.
