# Operations

[中文页面](operations.zh-CN.md)

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

It covers tests, lint, type checks, CLI help synchronization, package coverage, scripts, and public-boundary checks. CI does not fetch real market data, call Feishu, or use broker credentials.
