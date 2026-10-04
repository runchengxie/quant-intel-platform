# Reviewed U.S. News Revision Implementation Plan

> For agentic workers: REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

Goal: accept honestly dated background evidence and append reviewed news without
refetching or modifying existing market facts.

Architecture: extend the public owner's existing evidence and artifact contracts,
then add an offline branch to `dm daily-report`. The website and private deployment
validator consume the same versioned artifact. Normal market generation stays
independent of this branch.

Tech Stack: Python dataclasses, argparse, zoneinfo, pytest, Astro/TypeScript,
Node tests, Playwright. No new runtime dependency.

Spec: `docs/superpowers/specs/2026-10-03-us-news-revision-design.md`.

Status: approved for native inline implementation on October 4. Tasks 1–3 are
implemented. Task 4 validation and provider review are underway. Task 5 follows
the provider merge. Production activation remains out of scope.

## Global Constraints

- Introduce explicit publication precision for reviewed events in report schema `1.1`.
- Continue accepting existing `1.0` precise-time artifacts unchanged.
- Retain the complete facts array exactly, including order, values, quality, sources, observation dates, and retrieval timestamps.
- Keep the original `as_of` as the market-fact cutoff.
- `generated_at` records the actual revision assembly time.
- No current report, production configuration, timer, or Feishu receipt changes during development and no-send acceptance.
- Root daily-report tests and full owner gate pass. Website coverage remains at least 85%, browser checks pass, and deployment smoke tests pass before release.
- Merge the provider before its consumer. Cross-repository consumption uses installed public CLI or versioned artifacts, never sibling-source imports.
- Use separate task branches/worktrees. Generated fixtures, logs, archives and validation outputs stay outside repositories, except authored test fixtures.

## Review Focus

- Timestamp versus filing-acceptance ambiguity: original publication cannot be inferred from filing acceptance. Task 1 pins separate time roles.
- Unknown-zone or DST date intervals: do not assume 24 hours or the issuer's headquarters timezone. Task 1 tests both extremes and DST.
- Valid JSON with tampered lineage or null event time: both consumer validators must reject invalid metadata before publication. Tasks 3 and 5 test this.
- Symlinked/overlapping input and output paths: a failed offline revision must leave its original report and destination unchanged. Task 2 tests resolved paths and prewrite failure.
- English source-language fallback and missing sections: one approved macro item must not hide company-news gaps or produce partial translated prose. Task 4 tests rendered outputs.

## File and interface map

Public owner `quant-intel-platform`:

- Create `src/daily_messenger/daily_report/publication_time.py`: publication evidence intervals and validation.
- Create `src/daily_messenger/daily_report/news_revision.py`: offline revision assembly and provenance.
- Modify `models.py`, `reviewed_research.py`, `web_research.py` in that package: preserve legacy serialization and consume date-only candidates.
- Modify `src/daily_messenger/cli.py`: early offline dispatch, flags and safe errors.
- Modify `src/daily_messenger/daily_report/serialization.py` and `pipeline.py`: share the existing hash contract without changing normal collection behavior.
- Modify `src/market_intel_publication/us_daily_contract.py` and `import_market_daily_report.py`: public projection, manifest and new revision validation.
- Modify `src/daily_messenger/daily_report/render.py`, `web/src/lib/locale.ts`, `market-daily-utils.ts`, `market-daily-utils.js`, and relevant report sections in `web/src/pages/index.astro` and `web/src/pages/en/index.astro`: time precision and empty-news presentation.
- Modify `docs/how-to/reviewed-us-daily.md` and generated CLI help through `project_tools/update_cli_help.py`.

Private consumer `quant-intel-deploy`:

- Modify `scripts/validate_daily_market_report.py` and `us_daily_completeness.py`: verify schema1.1 and revision-specific monotonicity.
- Create `tests/smoke/test_us_news_revision.py`: consume an installed merged provider artifact without importing provider source.
- Modify `docs/production-migration.md`: no-send staging/rollback procedure, not automatic activation.

## Task 1: Publication precision and reviewed intake

Files: create `publication_time.py`; modify `models.py`, `reviewed_research.py`,
`web_research.py`; create `tests/daily_report/test_publication_time.py`; extend
`test_models.py`, `test_reviewed_research.py`, `test_web_research.py`.

Interfaces:

- Produce `PublicationTime` frozen dataclass with `precision: str`,
  `source_time: datetime | None`, `source_date: str | None`,
  `source_timezone: str | None`, `time_role: str`, `usage: str`.
- Produce `publication_interval(evidence: PublicationTime) -> tuple[datetime, datetime]`
  as UTC bounds. Date intervals are half-open. For precise evidence, both bounds
  are the same instant.
- Produce `validate_publication_time(evidence: PublicationTime, *, market_date: str,
  cutoff: datetime, section: str) -> None` and
  `publication_time_from_candidate(candidate: dict) -> PublicationTime`.
- Consume existing `load_reviewed_research` arguments unchanged. Add keyword
  `news_only: bool | NewsOnlyReview = False` for new-mode evidence IDs and
  approval requirements. `NewsOnlyReview` carries the actual UTC review instant
  independently of the source cutoff.

- [ ] Write `test_unknown_timezone_bounds_are_conservative`: source date
  `2026-10-02`, timezone `unknown` gives bounds `2026-10-01T10:00:00Z`
  and `2026-10-03T12:00:00Z`. Assert cutoff `2026-10-03T08:00:00Z` is rejected.
- [ ] Write `test_dst_day_uses_local_midnight_boundaries`: New York
  `2026-11-01` has a 25-hour interval, not 24 hours.

  ```python
  def test_dst_day_uses_local_midnight_boundaries():
      evidence = PublicationTime("date", None, "2026-11-01",
                                 "America/New_York", "publication", "background")
      start, end = publication_interval(evidence)
      assert start.isoformat() == "2026-11-01T04:00:00+00:00"
      assert end.isoformat() == "2026-11-02T05:00:00+00:00"
      assert (end - start).total_seconds() == 25 * 3600
  ```
- [ ] Write tests rejecting invalid IANA zones, naive timestamps, conflicting
  timestamp/date fields, future dates, date-only close/index/mover evidence, and
  treating filing acceptance as original publication. Assert source time remains
  null for accepted date-only macro/company background.
- [ ] Run `uv run pytest tests/daily_report/test_publication_time.py -v`.
  Expected: new contract tests fail before implementation.
- [ ] Implement helpers with `zoneinfo`, strict ISO calendar dates, unknown-zone
  bounds, and explicit `timestamp`/`date`, `publication`/`filing_acceptance`,
  `background`/`context` fields. Legacy candidates still use `published_at`.
  Date-only candidates use `publication_precision`, `source_date`,
  `source_timezone`, `time_role`, `usage`, and no fabricated `published_at`.
- [ ] Extend `MarketEvent` with nullable time and optional evidence fields.
  Default legacy fields are omitted from serialization. New date-only events
  include precision/date/zone/role/usage. Do not weaken `MarketFact` timestamps.
- [ ] For new-mode approvals require `source_locator`, `verified_facts`, and
  `display_basis` containing `basis`, `scope`, `source_url`, `verified_on`.
  These remain private and are not interpreted as model approval.
  Namespace new IDs as `reviewed.<full-draft-sha256>.<index>` only in news-only
  mode. Legacy `reviewed.<index>` behavior remains unchanged.
- [ ] Update candidate collection validation to accept explicit date-only
  background while retaining `needs_review`. No prompt may guess minutes or zones.
- [ ] Run `uv run pytest tests/daily_report -v`.
  Expected: new and legacy tests pass, legacy hashes/projections unchanged.
- [ ] Commit task 1 with its tests and contract documentation.

## Task 2: Offline revision and CLI

Files: create `news_revision.py`, `tests/daily_report/test_news_revision.py`;
modify `cli.py`, `serialization.py`, `pipeline.py`, `tests/test_cli_pipeline.py`,
`test_serialization.py`, and CLI help.

Interfaces:

- Consume Task 1 reviewed intake in `news_only=True` mode.
- Produce `content_digest(payload: dict) -> str` in `serialization.py`, extracting
  the existing pipeline hash rules. Normalize known timestamp fields to the same
  datetime representation as legacy hashing, clear `content_hash`, and preserve
  unknown fields. The ordinary pipeline delegates only hashing to this helper.
- Produce `NewsRevisionResult` with `changed: bool`, `artifact_path: Path | None`,
  `content_hash: str`, `added_claims: int`.
- Produce `revise_news(inputs: tuple[Path, Path, Path, Path],
  output_dir: Path, *, market_date: str,
  news_cutoff: datetime, revised_at: datetime) -> NewsRevisionResult`.
  Input order is report, manifest, draft, review. Grouping inputs complies with
  the repository's argument-count ratchet without changing CLI flags.
- Persist `quality_summary.revision = news_only` and `news_revision` metadata:
  `input_report_sha256`, `previous_content_hash`, `news_cutoff`, `revised_at`.
  Preserve earlier review lineage as an append-only revision chain.

- [ ] Write `test_revision_preserves_all_facts_and_nonresearch_status`: compare
  complete arrays/dicts, not just IDs or selected prices. Assert input bytes
  unchanged, original `as_of` retained and new `generated_at` explicit.
- [ ] Write `test_content_digest_matches_legacy_report_hash`: assert the shared
  helper gives the existing stored digest for authored legacy fixtures, whether
  their known timestamps are parsed datetimes or serialized ISO strings.
- [ ] Write `test_offline_cli_never_loads_credentials_or_fetches`: install failing
  guards on supplier fetches, configuration loading, subprocess model runners,
  socket connections and send entry points. Assert real CLI still produces the
  staged artifact. Guard external effects without mocking revision assembly.
- [ ] Write `test_repeat_is_noop`, `test_evidence_identity_conflict_is_rejected`,
  and rejection tests for tampered manifest/hash, incomplete decisions, attempted
  `index_returns`/`index_evidence`/`ticker`, output overlap through symlinks,
  and a pre-existing output report. Assert no writes on failure.
- [ ] Run `uv run pytest tests/daily_report/test_news_revision.py -v`.
  Expected: revision function/flag tests fail before implementation.
- [ ] Implement revision from validated raw artifact payloads so exact original
  fact strings/order/provenance survive. Use owner serialization/hash helpers,
  preserve old claims/events and section fact references. Change only research
  status, its missing-source entry, appended claims and revision metadata.
  Do not auto-upgrade unrelated quality or remove genuine optional gaps.
- [ ] Validate all inputs and construct/hash the full result before writes.
  Require a new staging destination, write no output for no-op, and never replace
  source files. Identical existing IDs are no-op, differing content is an error.
- [ ] Add `--revise-news`, `--input-manifest`, and `--news-cutoff` flags to
  `daily-report`. Default cutoff is actual revision time. Dispatch this branch
  before live pipeline imports/provider loading. Require both review paths and
  explicit matching date. Reject `--backfill` and unrelated mode combinations.
- [ ] Run `uv run pytest tests/daily_report tests/test_cli_pipeline.py -v` and
  `uv run python project_tools/update_cli_help.py --check` after regenerating help.
  Expected: all pass, failures leave originals unchanged and log no secrets.
- [ ] Commit task 2.

## Task 3: Public contract, lineage and downloads

Files: modify `us_daily_contract.py`, `import_market_daily_report.py`, `render.py`;
extend `web/tests/test_import_market_daily_report.py` and root `test_render.py`.

Interfaces: consume schema1.1 events and Task 2 revision metadata. Expose
precision/date/zone/role/usage and verified precise source time on schema1.1 public
events. Retain schema1.0 projection unchanged. Keep public manifests and report
hashes fail-closed, without publishing private review records or paths.

- [ ] Write `test_legacy_public_projection_is_unchanged` and
  `test_news_revision_keeps_distinct_market_and_news_times`. Assert all original
  facts equal input and that public lineage uses hashes, not private filenames.
- [ ] Write rejection tests for null time with missing date precision, inconsistent
  interval/cutoff, revision before original generation, invalid lineage digests,
  and fact-changing revision metadata. Verify protected lineage using the
  original versioned artifact when validating an actual revision transaction.
- [ ] Run `cd web && python -m pytest tests/test_import_market_daily_report.py -v`.
  Expected: new cases fail before implementation.
- [ ] Extend validation and selective projection for1.1, retain1.0 defaults.
  Apply original cutoff to facts and explicit news cutoff to new events. Never
  allow a news-only label to bypass fact/source/date validation.
- [ ] Render original market cutoff, news revised-at, publication date/precision
  and unavailable sections in Markdown/plain-text downloads. Preserve source links.
- [ ] Run root daily-report and website Python suites.
  Expected: legacy snapshots remain compatible, website coverage at least85%.
- [ ] Commit task 3.

## Task 4: Bilingual web and SVG presentation

Files: modify `locale.ts`, `market-daily-utils.ts`, its legacyJS parity module,
the US sections in both homepage files; extend `web/tests/market-daily-utils.test.cjs`
and `web/browser-tests/public-site.spec.ts`.

Interfaces: consume Task 3 public events and revision metadata. Translate stable
labels in locale catalogs only. Summaries retain event publication precision and
time-role metadata for both page and SVG consumers.

- [ ] Write `test_date_only_background_has_no_invented_clock`: English/Chinese
  SVG and page show source date, date-only label and unknown-zone label, with no
  midnight or fabricated minute. Assert underlying numerical facts unchanged.
- [ ] Write `test_partial_news_retains_empty_section_labels` and unknown-English
  paragraph fallback assertions. Assert one macro claim does not fill drivers or
  company news and no word-by-word partial translation is emitted.
- [ ] Run `cd web && npm test`.
  Expected: the new presentation cases fail before implementation.
- [ ] Implement full-paragraph translation/fallback and complete locale labels,
  separate original fact time from news revision time, and preserve legacy parity.
- [ ] Run `npm test`, `npm run check`, website Python suite and
  `npm run test:browser`. Build into an external validation directory.
  Expected: all pass with readable mobile layout and working PNG/source downloads.
- [ ] Update `docs/how-to/reviewed-us-daily.md`: flag examples, staging-only
  boundaries, date-only rules, no-op, review provenance and retained quotations.
- [ ] Run the full owner gate, perform fresh whole-branch review, push provider
  PR and merge only after required checks pass. Commit task4 changes before push.

## Task 5: Private consumer verification

Start only after the provider is merged. Fetch deploy and create a separate task
worktree from its main. Read its AGENTS.md. Do not trigger its private Actions.

Files: modify `scripts/validate_daily_market_report.py`, `us_daily_completeness.py`,
`docs/production-migration.md`; create `tests/smoke/test_us_news_revision.py`;
extend `test_daily_report_publish.py` and `test_personal_daily_image_delivery.py`.

Interfaces: consume merged installed provider CLI and versioned report1.1.
No sibling-source imports. Existing report/manifest contract and publisher
transaction remain the promotion mechanism.

Install the merged provider wheel into an isolated validation environment outside
the repositories. Do not install into the production environment or change its
pins. Record the provider merge SHA and wheel hash in acceptance evidence.

- [ ] Write `test_consumer_accepts_preserved_fact_news_revision` by invoking the
  installed CLI against private authored fixtures. Assert exact facts preserved,
  lineage links to original bytes, and no network/send operations.
- [ ] Write tests rejecting date-only cutoff crossings, tampered lineage,
  changed fact values/provenance/order, removed prior claims and old schema
  incompatibilities. Assert same-date personal sent receipts remain unchanged
  and delivery identity is independent of revised content hashes.
- [ ] Run `uv run pytest tests/smoke/test_us_news_revision.py -v`.
  Expected: new consumer cases fail before implementation.
- [ ] Implement consumer checks using versioned artifacts/public CLI. For
  news-only promotion require full fact-array equality and prior-claim retention,
  not just monotonic available-ID sets. Validate lineage against retained original
  artifacts. Do not relax existing generic publication checks.
- [ ] Document staging command, input backup, locked promotion, rollback and
  independent scoped production authorization. Do not install a new timer.
- [ ] Run deploy's documented complete local gates and affected smoke suite.
  Expected: all pass without privateCI, real supplier calls or messages.
- [ ] Commit, push and merge consumer PR after local gates and review pass.

## Execution and acceptance handoff

After plan review, implement tasks in this order. Recommendation: native inline
execution, because the five tasks share evidence/schema interfaces and the user
has been iterating in this session. A fresh whole-branch reviewer is still required.

Reassess company-source candidates only after both contracts work. Save a new
private hash-bound draft/review pair, establish display basis independently, and
run the offline CLI into a new external staging directory. Do not edit the
already published October2 artifact, bypass source review, or claim that all
eight candidates now qualify.

The handoff reports PRs, merge SHAs, exact checks, private acceptance evidence,
and remaining source-use blockers. Production code/pin changes, runtime
promotion and unattended scheduling are a separate authorized step. No messages
or delivery receipt resets are part of this plan.
