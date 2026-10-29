# Overseas theme evidence consumption

Reports consume owner research as retrospective evidence, separately from today's overseas
observations. They do not convert evidence into daily forecasts or ETF recommendations.

The boundary is `overseas_theme_evidence.v1`, copied verbatim from the research owner's
`docs/contracts/overseas_theme_evidence.v1.schema.json`. The provider revision is recorded in
each artifact's `source_revision`; the caller separately pins the entire artifact's SHA-256.
The schema snapshot is [available here](contracts/overseas_theme_evidence.v1.schema.json).

`research_contracts.overseas_theme.load_evidence(path, expected_sha256, observed_at)` reads at most
2 MiB, checks the pin before parsing, rejects duplicate JSON keys, and validates required types,
source ID/hash identity, HTTP(S) source links, unique evidence IDs, finite error gains, ordered
intervals, and timezone-aware clocks. Generation must be UTC and cannot follow observation;
sample dates must be ordered and cannot follow generation in Asia/Shanghai. Source revisions
must be full 40-character lowercase Git hashes. Evidence remains exploratory and historical
point-in-time certification must be false. Only gap, post-open and next-tradable-open outcomes
and zero/one-session lags are accepted.

`a_share_daily.overseas_theme_report.render_evidence` renders every comparison, including negative
gains, with sample dates, generation time, revision, evidence IDs, source URLs/hashes and owner
limitations. Gains are reported as provided, without recalculation. Positive gains mean lower MSE;
intervals spanning zero do not establish improvement. English is the fallback locale; Chinese
is supported. The localized presentation catalog lives in that module.

Missing evidence and validation rejection visibly fall back to observations. Rejection messages use
stable codes, not local paths or parser details. `EvidenceError` subclasses `ValueError`; callers
should catch it and pass its string code to the renderer. The caller supplies an explicit aware
observation time and trusted pin; a digest found beside an untrusted file is not authentication.
The reader does not fetch URLs or independently certify source datasets.

Run `uv run pytest tests/test_overseas_theme_evidence.py` for isolated contract and rendering tests.


## Rendering a morning report

```bash
uv run a-share-daily morning-report --manifest /external/morning_manifest.json \
  --news /external/market_news.json --out /external/morning_report.md \
  --overseas-theme-evidence /external/overseas_theme_evidence.v1.json \
  --overseas-theme-sha256 <reviewed-artifact-sha256> --locale en-US
```

The local manifest can instead contain `overseas_theme_evidence: {"path": "...", "sha256": "..."}`.
CLI arguments override that pointer. The renderer always validates the referenced bytes; manifest
fields do not bypass validation. Missing/invalid inputs remain visible in the report. No send occurs
unless explicitly requested with the existing delivery option.

The generation clock is aware and converted to Asia/Shanghai. Morning observations freeze at the
earlier of generation time and 08:45 on the report's decision date; an input manifest's data date
does not replace the generation date. Historical replay must supply an explicit `generated_at`
to `render_morning_report`. A-share pre-open, intraday, post-close and holiday context uses XSHG;
overseas quotes use each exchange's latest completed session, including holidays and DST. The
morning pipeline passes its cutoff to quote selection; general daily-close callers retain their
existing requested-session behavior. Source close times do not certify historical retrieval.

Manual industry associations are versioned `overseas_concepts.v1`, with human weights retained.
They are descriptive, not calibrated forecasts. Old stored bullish/bearish labels do not become
current predictions; unverified legacy provenance is explicitly marked. No ETF holdings mapping
is invented. Nonfinite, malformed, future, missing-date or stale observations do not contribute
at the decision cutoff. Report sources show evidence IDs, URLs, session dates and close times.

Schema provider: [quant-market-research f918f283](https://github.com/runchengxie/quant-market-research/blob/f918f2832938743bd743021a7dfd89590e6af002/docs/contracts/overseas_theme_evidence.v1.schema.json).
The snapshot SHA-256 is `4282b0c855633a53096c2c9a7947cd27f761bac7498a2a0ba7e70144b85c883b`.
The schema is embedded in the installed consumer module, with a parity test against the snapshot.
The research and report implementations exchange files only; no research source is imported.

## Active evening reports

The active `a-share-daily evening` and `review` commands accept
`--overseas-theme-evidence PATH --overseas-theme-sha256 SHA256`. Deployment can
supply the defaults through `OVERSEAS_THEME_EVIDENCE_PATH` and
`OVERSEAS_THEME_EVIDENCE_SHA256`; explicit command arguments take precedence.
The public report refresh also uses this active CLI and inherits those defaults.

Markdown appends the existing retrospective evidence section, preserving every
comparison, source and limitation. JSON exposes `overseas_theme_research` with
`status`, `evidence_cutoff_utc`, `rejection` and `evidence`. Missing or rejected input
leaves the market facts intact and displays an explicit unavailable state. The
cutoff is the earlier of actual generation time and the requested report date's
end in Asia/Shanghai: historical backfills cannot consume later-generated
research. This is a separate retrospective study, never a daily forecast or a
strategy promotion. Report generation does not send messages unless the existing
explicit delivery flag is supplied.
