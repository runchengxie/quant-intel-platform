# Treasury observation calendar implementation plan

**Goal:** Check Treasury yields against their own expected observation day, refresh the 2026-10-12 reference from 2026-10-08 to 2026-10-09, and preserve real dates and nonzero last-session moves.

**Architecture:** Platform owns a reviewed bond/publication calendar and the expected-observation API. Collection queries the official Treasury source at that date, then FRED as fallback. Deploy consumes the installed package calendar artifact for monitoring and validation without child processes. Report renderers disclose closure and reference dates without relabeling reference changes as report-day moves.

**Scope:** User-approved four-point design in this conversation. Keep source URLs/timestamps and content hashes; preserve unrelated facts and reviewed claims when revising the existing report. Provider PR merges before consumer pins. Existing production dependency differences require release-pair preflight and rollback checks before switching.

- [ ] Add calendar and regression cases: Columbus Day, Veterans Day, ordinary sessions, weekends/month boundaries, early close, uncovered years.
- [ ] Query Treasury using expected observation date; compute moves from two adjacent expected sessions and retain true dates. Failed or stale sources stay explicit.
- [ ] Extend publication/rendering contracts for validated holiday references; tests forbid fabricated same-day/zero changes.
- [ ] Update Deploy completeness, promotion and alerts to use owner dates; lagged references meeting expected date pass, older data does not.
- [ ] Run owner and consumer quality gates, merge provider then consumer PRs, deploy matched releases with rollback retained.
- [ ] Refresh only Treasury facts in the current report through owner collection, validate/publish the revision, reconcile monitor state, and verify actual online content.
