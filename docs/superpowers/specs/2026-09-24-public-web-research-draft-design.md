# Public-web research draft for the US market daily report

## Intent and scope

The daily report should approach the six-section desk-wrap example without waiting for one market-data vendor. A scheduled Codex run may locate public articles describing the close, market drivers, macro releases, company news, and notable movers. This change creates an internal, review-required research draft. It does not turn a news article into a licensed quote feed or auto-publish model output.

## Contract

`dm research --date YYYY-MM-DD --out ABSOLUTE_DIRECTORY` runs Codex CLI with live search and a strict JSON output schema. The target date is the US market observation date, not the search or article date. Each candidate has a section, original URL, article title, source publication timestamp with timezone, explicit observation date, brief original-language paraphrase, and a concise supporting passage. The run receipt records generation time, cutoff, model, counts, and rejected-candidate reasons. Raw model output and the validated draft remain outside Git and public Pages data.

Candidates are rejected when URL is not HTTP(S), publication time is missing or later than cutoff, observation date differs from the requested market date, section is unknown, or supporting passage is absent. Every accepted candidate is still marked `needs_review`; validation only checks the structural and time boundaries, not whether the webpage truly supports the statement. A failed model call or invalid output exits nonzero and cannot overwrite a prior good draft. Re-running the same date writes a uniquely named receipt, not a mutable daily report artifact.

## Operational boundary

Use Codex CLI's authenticated account rather than adding an API key. The CLI is invoked read-only, without bypass flags, with `--search` and a timeout. The scheduler is a separate deployment concern and must point to a stable production release, not a temporary worktree. The first live run is manual; automatic promotion to the public report requires a later evidence-verification gate. Public prose will cite URLs and paraphrase, not reproduce articles.

## Verification

Offline tests cover the exact CLI invocation and prompt, date/cutoff/URL filtering, malformed output, timeout/nonzero exit, and preservation of earlier drafts. Run daily-report tests and the repository's full quality gate. A manual live run for a known completed US trading date checks whether the CLI can actually browse and produce reviewable candidates.
