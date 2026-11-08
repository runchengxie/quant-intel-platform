# Operations

[Chinese version](operations.zh-CN.md)

## Failure semantics

When data is incomplete or an external service is unavailable, the platform records a degraded state and stops downstream processing when it cannot safely produce a result. Success, degraded, and failure outcomes must all be represented by inspectable receipts.

## Deployment boundary

Host timers, production credentials, real delivery targets, and runtime state are managed by `quant-intel-deploy`. The public repository provides reusable code, contracts, and offline checks only.

## Recovery and scheduling

Use the documented `dm`, `a-share-daily`, and recovery scripts through stable production paths. Do not point scheduled jobs at temporary worktrees. After changing production paths, reload the relevant systemd units and run the matching offline or shadow smoke test.

## Quality gate

The repository gate is:

```bash
uv run python project_tools/check_all.py --scope all
```

It covers tests, lint, type checks, CLI help synchronization, package coverage, and scripts. CI runs public-boundary checks separately. CI does not fetch real market data, call Feishu, or use broker credentials.

### Weekly basket personal delivery

Pass `--personal-only` with `a-share-daily weekly-basket --send` to deliver only
to the explicit `--personal-chat-id`. This ignores any configured group target
and does not require `--group-chat-id`. Without this flag, sending continues to
require and deliver to both personal and group targets. Personal receipts and
idempotency keys remain the same when switching between these modes.


### Weekly basket delivery v2 migration

The source implementation requires `--sender-scope` (or
`WEEKLY_BASKET_SENDER_SCOPE`) for `--send`. Supply a stable, explicit identifier
for the sending account. This declaration binds local attempts; it does not
verify the account authenticated by the external CLI. Keep `--state-root` stable:
canonical delivery state is stored under its `delivery/` directory. The output
root is also the explicit search root for historical date-scoped receipts.
Changing roots does not authorize sending again. Durable live delivery and render
locking require a POSIX host with filesystem support for `flock` and directory
`fsync`; unsupported hosts must not be used for live delivery.

Text and image have separate durable outcomes. `sent` means every requested
phase was reported accepted by the CLI with a message ID, not that a recipient
read it. A malformed CLI response, timeout, interrupted inflight attempt, or
changed payload holds the attempt without automatic retry. Historical receipts
remain unchanged and return `legacy_unverified` / `hold_no_send`, including old
`failed` and `dry_run` receipts. There is no automatic migration or resend tool.
An operator must review those holds separately before any future reopening.

Rendering returns immutable bundle paths and a hash manifest. Existing
`report.md`, `basket.csv`, and `report.png` aliases remain available to readers;
delivery uses the frozen bundle and private snapshot, never a later alias.
Dry runs return their actual artifact paths under unique `previews/` directories
and leave canonical basket and delivery state untouched. Previews still read the
authoritative previous basket and reuse the current weekly freeze; an explicit
override changes preview state only. Consumers should read
the returned paths rather than assume a dry run writes the live date directory.

These are source contracts only. A production rollout requires the Deploy owner
to configure the sender scope, preserve existing state and historical receipt
roots, and validate the provider and consumer revisions together before enabling
real transport. Do not activate or retry a historical hold merely because this
source version has merged.
