# Weekly Pages and image-only publication design / execution contract

User authorized: publish the weekly market/style research to existing public Pages, retain private customer/recipient/runtime data, align generation/build/publication/live-verification/image-delivery flow with daily reports. Feishu sends exactly one image per report, no text/title/link message. Preserve per-target idempotency and uncertain-outcome blocking. User delegates remaining design choices.

Architecture: Platform owns public bundle export/import/validation and snapshot handoff. Pages owns bilingual navigation and weekly reading pages, static image download and lazy ECharts. Deploy owns private configuration, staged publication transaction, exact live identity checks, scheduler and receipts. Do not copy research calculations. No credentials/recipient IDs/private paths in public artifacts. Never publish raw owner JSON wholesale.

Weekly identity: report_id = YYYY-MM-DD-weekly; date = Friday/trading cutoff ISO date. Public schema `market_intel_pages.weekly_recap.v1`. Payload exact fields:
- schema_version, publication='public', report_id, date, generated_at (aware ISO timestamp)
- content_hash: SHA256 of UTF8 canonical JSON of entire payload excluding content_hash (sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).
- markdown: complete approved public market/style report, bounded text; render as sanitized Markdown, never executable HTML.
- source_url='reports/YYYY-MM-DD-weekly.md'
- image: {source_url:'reports/YYYY-MM-DD-weekly.png',sha256:<64hex>,width:<positive int>,height:<positive int>}
- summary: {value_regime:<owner enum string>,value_streak_weeks:<int>,value_return_12w_percent:<finite number>,small_crowding:<0..1>,large_crowding:<0..1>,size_signal:<owner enum string>}
- series: {value:[{date:<ISO>,return_12w_percent:<finite>,wealth_index:<finite positive>}],size:[{date:<ISO>,relative_strength:<finite positive>,small_crowding:<0..1>,large_crowding:<0..1>}]}. Allowlist, ordered unique dates <= report date, last point == report date, at most 104 value weekly observations and 252 size daily observations. Data already exists in research-owned artifacts: value weekly_features date/ret_12w/cum, size series date/relative_strength/small/large. ret_12w multiplied by 100 only as unit conversion.
- sources: {value:{schema_version:'research.weekly_analysis.v1',as_of:<ISO>,sha256:<64hex>},size:{same}}. Hash original admitted artifacts, never expose paths.

Bundle: external directory containing weekly_recap.json, YYYY-MM-DD-weekly.md and YYYY-MM-DD-weekly.png. CLI export validates owner artifact types/as_of/quality passed and date match; PNG is bounded and real. Explicit --publication public required. Hashes bind all published content. Reject stale dates, mismatched image or Markdown, private/unexpected fields, symlink/path traversal/non-finite or oversized input.

Platform APIs / CLI exact:
- market-export-weekly-recap --report PATH --image PATH --value-artifact PATH --size-artifact PATH --date YYYY-MM-DD --output DIR --publication public
- market-import-weekly-recap --bundle DIR --root PAGES_ROOT [--dry-run]
- public Python validation: market_intel_publication.weekly_recap_contract.validate_weekly_recap(payload: object) -> dict; canonical digest helper content_hash(payload: dict) -> str. Validate without importing any sibling repo.
- Pages artifacts: artifacts/public/data/weekly_recap.json (latest payload), artifacts/public/data/weekly_recaps.json (index {schema_version:'market_intel_pages.weekly_recaps.v1',reports:[payload newest first]}); artifacts/public/reports/<date>-weekly.md and .png. Keep <=5 weekly dates; full private history stays external. Import stages changes and validates before replace, preserve unrelated daily files. Snapshot CLI exports only validated allowlisted weekly records and hash-bound files. Daily history must not prune weekly files accidentally.

Pages:
- weekly landing: /weekly/ and /en/weekly/; detail /weekly/<date>/ and /en/weekly/<date>/ (Astro base remains /quant-intel-pages).
- English first default / explicit locale switch preserving weekly route; existing site language behavior unchanged. New translatable UI in semantic-key locale catalog, no untranslated UI in components. Chinese report text can be explicit source-language fallback in English.
- Add discoverable weekly link/entry from existing home/header. Static published PNG + full sanitized report + date/data/source limitations. Download exact public PNG. Server validate schema and hash using same canonical JSON contract; do not rely on producer only. Static image visible without JS.
- Optional lazy interactive weekly component on detail page only, use existing ECharts dependency. Value history and size strength/crowding, hover/zoom/legend; expose units, observation dates, factual series only. No new analytics or client computation beyond presentation/unit selection. Independent static fallback and accessible tables; browser and chart-data tests. Avoid main-page bundle regression.

Deploy:
- weekly producer remains stable weekly_recap.sh but production scheduling must generate --no-send bundle first. No direct send before verified Pages publication.
- New weekly-specific publisher uses existing retry/auth/private-files/locks and same transaction semantics as daily (candidate -> immutable snapshot -> restricted-path commit/PR -> required checks -> current-main merge/revalidate -> Pages deployment -> live content/image SHA -> deployed receipt -> cleanup). May reuse shared class/hooks where appropriate; do not introduce a dependency on sibling source or break existing daily paths. Must reconcile remote writes before retrying. Preserve existing daily files and publisher concurrency safety; dedicated checkout/state. Use installed pinned Platform CLI after provider is merged.
- Existing weekly_image_delivery receipt identity target+date retained, so already-sent October 23 recipients MUST NOT receive duplicates when publishing historical current report. Verification of exact public content/image precedes calls to existing image delivery. Same configured formal weekly audience only. Weekly freshness uses report cutoff, Saturday schedule, bounded recovery; no stale previous-week send. Retry publisher timer at Saturday 09:00..11:55 every 5m, no boot catch-up. Existing generation weekly timer remains 09:00 invoking no-send generation then bundle export; online publication then image delivery happen in recovery publisher, without rebuilding report each poll.
- Image-only daily messenger: replace parent text+reply with one direct image message while keeping existing success/uncertain receipts and backend idempotency. Do not reset or backfill today's already-sent daily/weekly records. Tests assert exactly one image command and valid message ID, no text or reply command.
- Credentials/config/logs/state external. Configure production only after provider/consumer PRs merged and validated. Record source revisions tested together and rollback targets. No unrelated scheduler reinstalls/current updates. No bypass of hooks or GitHub required checks. Private deployment Actions not triggered.

Execution:
1. Platform task: add contract+export/import+snapshot+schema/tests/docs, full check_all and PR; provider merge before consumers pin.
2. Pages task: implement loader/locales/pages/interactive/browser tests against agreed fixtures in its task worktree. Run complete repo gates; pin merged Platform snapshot provider before release.
3. Deploy task: publisher/generation+send wiring/image-only daily/tests/docs in own task worktree. Full local gate and publish no-send/live checks. Pin merged provider. No remote production write until all required consumers merged.
4. Independent reviews, validate current target versions, merge provider -> Pages -> Deploy. Publish October23 public weekly artifact/site, verify live hash; retain already sent receipts without resend. Preview any new image/interactive views. Install producer/publisher timers, verify next times and no stale send. Clean only task branches/worktrees after merge; retain full private evidence outside repos.
