# Workflows

The public repository supports manual CLI execution and secret-free quality checks. Production scheduling is intentionally outside this repository.

## Public workflow stages

```text
owner CLI / versioned artifact
        ↓
validation and freshness checks
        ↓
report assembly and rendering
        ↓
optional injected delivery adapter
        ↓
receipt and audit output
```

GitHub Actions runs offline tests, lint, type checks, contract checks, rendering regressions, and package builds. It does not fetch real data, send messages, or commit generated snapshots.

## Private workflow stages

The private deployment repository supplies production schedules, data roots, credentials, owner CLI locations, recovery bridges, and delivery routing. It consumes a pinned public release.
