# Core concepts

[Chinese version](concepts.zh-CN.md)

## Market facts

Market facts are source-backed observations such as prices, volume, indexes, news, and trading dates. Each fact should retain a source, date, and status so that later readers can verify it.

## Research artifacts

Research artifacts are produced by `quant-research`, `quant-platform`, or `strategy-pipeline`, such as DailyWatch20 selections, factor results, and strategy receipts. Market Intel consumes these artifacts, validates dates, fields, and hashes, and then assembles reports.

## Reports and receipts

Reports are presentation products. Receipts record whether a step succeeded, degraded, or failed, together with the evidence and input versions needed for diagnosis. A report must not turn a missing source or failed validation into an unqualified market claim.

## Ownership

Market-intelligence ingestion, report rendering, dashboards, delivery, and recovery belong here. Market data, research algorithms, backtests, strategy runtime, and execution belong to their owner repositories. Cross-repository integration uses public CLI contracts or versioned artifacts, not imports of another repository's business source.
