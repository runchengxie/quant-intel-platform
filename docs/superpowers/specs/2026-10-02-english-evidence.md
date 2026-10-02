# English report evidence repair

Restore the English daily-report presentation without changing its canonical market facts, publication dates, approved claims, sources or private delivery state.

## Requirements

- Preserve explicit currencies. `亿美元` must display as USD, `亿元` as CNY, and an unqualified `亿` must not invent a currency. Keep numeric magnitudes unchanged when using a 100-million unit.
- Keep the October 1 reviewed research readable in English through exact source-bound locale entries. Translate complete paragraphs before SVG wrapping. Unknown future prose remains intact rather than being partially rewritten or automatically approved.
- English source links must include reviewed claim sources as well as market fact sources, deduplicate URLs and preserve the existing HTTPS boundary.
- Restore existing Chinese-page features on the English homepage: report generation timestamp with an explicit time zone, current U.S./Asia PNG downloads and recent U.S. visual history. New labels belong in the locale catalog.
- Correct the stale chart-status documentation with dated evidence. Do not invent missing margin observations or sessions.
- Keep the current production runtime pair and scheduler unchanged. The existing public main Pages workflow deploys the merged static-site changes. No sends, model calls or historical report regeneration.

## Acceptance

Currency and pre-wrap regression tests, built-page citation/download/history tests, the complete Node and web Python suites, browser checks, root gate and remote required checks must pass. Independently review the final branch and verify the deployed English page after its normal Pages workflow succeeds.
