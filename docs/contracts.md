# Artifact contracts

[Chinese version](contracts.zh-CN.md)

The JSON structures in this repository define the minimum fields for important artifacts. A change that breaks these contracts is a breaking change.

Consumers should validate schema, artifact date, source freshness, and content hash before rendering or delivery. A missing, stale, or unverifiable artifact must produce a visible failure or degraded receipt; it must not be presented as a fresh successful report.

Cross-repository consumers use versioned files and public CLI contracts. They must not import business code from the owner repository. Keep evidence identifiers, source URLs, source times, publication status, and receipt fields stable and machine-readable.

## DailyWatch20 handoff

`quant-research` owns the DailyWatch20 producer in `strategy_app.daily_watch20`. `quant-intel-deploy` owns the production bridge and scheduling; `quant-intel-platform` validates, renders, and delivers the owner-published artifacts. The current selection contract uses `watchlist_20.csv` and `selection_receipt.json`, with `watchlist_20.json` as an optional companion. Consumers validate dates, receipt status, artifact hashes, row counts, and policy fields before delivery. See the Chinese companion for the detailed field and validation contract.

The legacy hot-sector signal fields (`raw_pred`, `signal_eval`, `signal_backtest`, and `candidate_universe.json` source-gate states) are retained only to identify historical research artifacts. They are not the current DailyWatch20 selection schema. The historical `strategy watchlist20 news-heat-export` command is also absent from the current `strategy` CLI; the installed owner interface is `daily-watch20-owner`. That owner's `run` command consumes a previously published optional news-heat artifact. The older `hotsector validate-output` and `strategy export-targets` flow does not define the current DailyWatch20 handoff.

The optional topic chart consumes the versioned `topic_summary.json` artifact published with the selection run. It does not treat legacy `hotsector/candidate_universe.json` as a topic summary.
