# Verified market report access for AI Agents

`quant-market-brief` reads an existing public daily report and emits a deterministic
`quant.market_brief.v1` JSON object. It uses the same content hash, public manifest,
source and market-date checks as the public daily-report importer. It does not
fetch data, regenerate reports, write files or send messages.

Install the package in your environment, and copy the repository's
`skills/quant-market-brief` folder into your Agent tool's skills directory. The
Skill calls the installed CLI; it does not maintain a second data or scoring layer.

```bash
quant-market-brief --input /path/to/bundle/daily_report.json \
  --manifest /path/to/bundle/publication.json --expected-date 2026-10-02
```

Use the original owner bundle, not the reduced public Pages projection. For a
news-only revision pass `--previous-report /path/to/immutable/daily_report.json`.
The requested date is the report's market date, not its UTC generation date.
“Latest” must be resolved by the caller using a known publication/archival source;
the CLI does not search production directories or silently choose an older file.

The output includes:

| Field | Meaning |
| --- | --- |
| `report_date`, `as_of`, `generated_at` | Requested report date, market cutoff and generation time |
| `source` | Bundle report filename and run ID |
| `artifact_hash`, `content_hash` | Exact input file SHA-256 and owner content hash |
| `data_quality`, `evidence_level`, `limitations` | Preserved quality, descriptive evidence stage and interpretation boundaries |
| `report` | Allowlisted public facts, reviewed claims, evidence IDs, sections, source status and missing sources |

Exit status is 0 on success; validation/read errors return 2, describe the error
on stderr and emit no JSON on stdout. Public claims must reference evidence in the
public projection with source URLs. Legacy id-only event projections are rejected
rather than treated as complete evidence. The file is read once, so its hash
always describes the bytes used for the output. Hash verification establishes consistency with the provided
manifest; it is not publisher authentication or independent fact verification.
No future-return prediction, counterargument, topic score or watchpoint outcome is
manufactured when absent from the report. The five-date Pages window remains
unchanged; longer comparisons require explicitly supplied retained bundles.

## Legacy scoring meanings

The existing keys, weights, arithmetic and totals remain compatible.
`breakdown_detail` now adds `metric`, `label`, `evidence_level` and `limitations`.
Digest HTML and summaries use the actual metric meaning, including when reading
legacy scores without these added fields.

| Theme | `fundamental` | `valuation` | `liquidity` | `event` |
| --- | --- | --- | --- | --- |
| AI | Theme performance | Average PE relative to 35 | Average PS relative to 8 | Fixed 70 |
| Magnificent 7 | Aggregate market cap relative to $11.5 trillion | Average PE relative to 32 | Average PS relative to 7 | Fixed 68 |
| BTC | Fixed 50 | Futures basis | ETF net inflow | Fixed 65 |

PS measures valuation; market cap measures size. Neither measures financial
quality or execution liquidity. BTC sentiment uses funding rates, while equity
sentiment uses the existing market sentiment aggregate. Missing inputs keep the
existing fallback flags and values; fixed constants are explicitly identified.
All scores remain descriptive heuristics without out-of-sample predictive
validation. This change corrects interpretation, not the underlying scoring model.
