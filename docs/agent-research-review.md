# Compare verified U.S. daily reports

`quant-research-review` describes changes between two original public daily-report
bundles. It reuses `quant-market-brief` validation for each report and compares
facts, report statements and quality gaps without generating new research claims.

```bash
quant-research-review \
  --baseline /path/to/baseline/daily_report.json \
  --baseline-manifest /path/to/baseline/publication.json --baseline-date 2026-10-02 \
  --current /path/to/current/daily_report.json \
  --current-manifest /path/to/current/publication.json --current-date 2026-10-05
```

For news revisions provide the immutable parent through `--baseline-parent` or
`--current-parent`. Dates and cutoffs must progress forward. A later version of
the same report date must have a strictly later generation time. An identical
snapshot is explicitly identified. Historical backfills may be generated later
than their market dates; report ordering does not establish point-in-time data
availability. No implicit archive lookup, source fetching or file output occurs.

The output schema is `quant.research_review.v1`:

| Field | Meaning |
| --- | --- |
| `report_kind`, `comparison_kind` | U.S. daily report; different dates, same-day revision, or identical snapshot |
| `baseline`, `current` | Report date, cutoff, generation time, owner run ID and hashes |
| `fact_changes` | Stable fact IDs, before/after values, absolute deltas and comparability status |
| `claim_changes` | Statements grouped by cited evidence IDs, marked added/removed/revised/unchanged |
| `data_quality` | Both quality summaries/source statuses, new gaps and resolved gaps |
| `evidence` | Public fact/event records indexed separately for each snapshot, including available provenance |
| `validation`, `limitations` | Descriptive interpretation boundaries; no watchpoint or predictive-performance results |

Fact deltas require unchanged metric, instrument, unit, source and source URL and
finite numeric values. A source/basis change prevents numeric comparison. For
percent-valued metrics, a move from 1% to 3% is **2 percentage points**, not a 2%
cumulative return. Other deltas use the original unit; no conversion is inferred.
Missing observations remain missing. Equal numbers may still have different
observation dates or quality; inspect the evidence and quality records.

Claim grouping describes report content, not semantic truth or hypothesis
success. Matching evidence IDs do not prove the same underlying event. Added
statements cite supplied evidence; removed statements are not refutations.
Ordering-only changes to source/reference lists are ignored. Evidence-ID
collisions between facts and events are rejected. Hash validation confirms
consistency with the supplied public manifests, not publisher identity or market
truth. Asia `insight → watchpoint → outcome` and backtest contracts remain separate.

Exit 0 returns JSON. Validation/read errors return 2 with diagnostic stderr and
no JSON on stdout. Install the distributable
[`quant-research-review` Skill](https://github.com/runchengxie/quant-intel-platform/tree/main/skills/quant-research-review)
in your Agent environment and use its installed CLI; do not import adjacent
repository source. Retained original bundles support longer comparisons without
expanding the five-date public Pages window.
