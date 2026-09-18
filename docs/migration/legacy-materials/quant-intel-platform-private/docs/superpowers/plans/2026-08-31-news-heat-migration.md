# News heat migration plan

## Goal

Move the `news_heat.csv` calculation and its source-data validation from
`market-intel/src/a_share_daily/news_heat.py` into `research-workspace/strategy-pipeline`.
`market-intel` should retain only a consumer-side contract loader and report fallback behavior.

## Scope

1. Define a versioned `news_heat` artifact contract with source dates, source lineage,
   quality status, and the stable CSV columns currently consumed by DailyWatch20.
2. Port the calculation and tests to strategy-pipeline; publish it beside the DailyWatch20
   run artifacts and add its hash to `selection_receipt.json`.
3. Change the DailyWatch20 producer to consume the local producer output rather than invoking
   market-intel Python code.
4. Add market-intel validation-only loading and preserve an explicit optional fallback when the
   artifact is absent.
5. Remove the old producer path after one successful production observation window.

## Non-goals

Do not move chart rendering, morning-report formatting, or delivery code. Do not infer news
entities from free text; preserve the current auditable upstream-source boundary.

## Verification

Run producer contract tests, receipt inventory/hash tests, market-intel consumer tests, and a
staging end-to-end publication followed by a morning chart dry run.
