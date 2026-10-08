# Capture a news source and preview six sections

Capture the complete StreetAccount feed before preparing a local preview. This command produces unreviewed files only. It does not create a publication manifest, send messages, approve sources or install a schedule.

## Capture or replay

Use an explicit expected XNYS trading date and a new output directory outside all source repositories:

```bash
uv run python -m daily_messenger.daily_report.news_snapshot \
  --date YYYY-MM-DD --output-dir /external/news-snapshots/new-run
```

The endpoint is fixed to `https://www.streetaccount.com/rss/rss.xml`. Requests use connection/read timeouts, reject redirects and cap the response at 1 MiB. The default preview has English headings and retains the original English source text.

For a reproducible replay, provide the original capture time explicitly:

```bash
uv run python -m daily_messenger.daily_report.news_snapshot \
  --date YYYY-MM-DD --input-rss /external/source.xml \
  --captured-at YYYY-MM-DDTHH:MM:SS+00:00 \
  --output-dir /external/news-snapshots/replay-run
```

The declared capture time is provenance supplied by the operator, not an independently attested publication time. Replay mode is recorded. Never replace an unknown capture time with the current time to make old news appear fresh.

## Files and trust boundaries

| File | Purpose |
| --- | --- |
| `source.xml` | Original response bytes, including a possible UTF8 BOM |
| `snapshot.json` | `market.news-snapshot.v1`: source hash, expected session, capture/build/item times, issues and source blocks |
| `preview.md` | Clearly marked local preview with six headings or a quarantine explanation |
| `editorial.json` | Optional editorial input, preserved for traceability |
| `receipt.json` | File hashes and completion receipt, written last; no source approval |

An existing destination is rejected. A successful process exit means the unreviewed bundle was generated. It does not mean the facts, causal explanations, timestamps or display permissions are approved. A bundle without its receipt is incomplete.

The command compares the channel build date with the expected New York session, checks the XNYS close (including holidays and early closes), and checks the weekday explicitly mentioned in the source. Date conflicts, preclose builds or a changed summary layout produce a quarantined bundle and exit code 2. Invalid XML, missing timestamps, oversized files and other input failures exit with code 1. Output directories inside source repositories are rejected.

The current layout recognizer is conservative: four recognizable summary bullets and gainers/decliners blocks. It has been exercised with one real sample and synthetic cases. It is not a general guarantee of future feed structure. Unexpected layouts require inspection rather than positional guessing.

StreetAccount item timestamps can precede the close despite describing closing results. They remain original item metadata. `published_at` stays null, and source approval stays unresolved. Channel build time and capture time must not be relabeled as publication time. This artifact is **not** compatible with reviewed `web_research` candidates or public report importers; the existing publication-time gate is unchanged.

## Optional Chinese editorial preview

Supply `--locale zh-CN --editor-json /external/editorial.json`. Locale selects headings only; it does not translate content automatically. The editorial JSON contains `source_sha256` and six ordered `sections` with keys `market`, `drivers`, `company_news`, `macro`, `gainers`, `losers`. For a full bulletin, each section contains `items`, an ordered array of objects with nonempty `text` and same-section `block_ids`. All source blocks must be covered in source order. Gainers and losers require exactly one entry per original mover. A market entry referencing only `market-title` renders as the index headline; other entries are numbered. Company news and macro paragraphs can reference the same original block across multiple entries. This verifies block coverage, not sentence-level completeness. The older section-level `text`/`block_ids` format remains accepted for compact previews; do not mix it with `items`.

The editor must preserve media attribution, actual versus planned events, currencies, units, signs, numeric ranges and conditions. Treat source material as data, not instructions. The program checks the source hash, section references, text bounds and unchanged numeric tokens. It can reject `1-3` changing to `13`, but it cannot certify semantic equivalence, unit consistency or causality. Exact K/M/B and Chinese 万/亿 scaling is supported, for example `$40B` to `400亿美元`. The validator also recognizes English number words zero to ten and explicit FY/timestamp short years. It checks numeric values, not currencies or units. Parenthesized declines in the original index headline may be rendered with a minus sign. Other signed values and ranges must remain unchanged. Edited files for quarantined sources are rejected.

No model is invoked by this command. A separately generated editorial input is still unreviewed. The first real Chinese sample was manually edited from a frozen source; it does not establish automatic translation quality.

## Next integration

Keep snapshots private while checking source-use permissions. Verify material claims against company releases, filings and official macro documents. Preserve the existing reviewed-research and publication gates. To use snapshots themselves as evidence, availability time requires an explicit contract extension distinct from publication time. A selectable six-section renderer can then keep gainers and decliners separate without replacing the current report.

## Full bulletin editorial contract

Retain company tickers, company names, attribution, financial periods, rating changes, guidance conditions and important numerical detail. Avoid replacing a detailed mover with a generic sentence such as “earnings beat”. Preserve the source's selected companies without padding to a fixed count. Split company and industry news into separate entries; a report about a financing or partnership may reference multiple tickers in the same entry. Do not infer a legal company identity from an unfamiliar ticker without verification.

For example, a mover entry can be `{"text": "XYZ +3.2%｜Company: ...", "block_ids": ["gainers-1"]}`. This input is prepared separately, manually or by an editor. The command still does not invoke a model or produce source approval.
