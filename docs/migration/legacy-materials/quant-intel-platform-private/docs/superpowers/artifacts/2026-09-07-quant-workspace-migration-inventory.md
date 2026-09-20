# Quant Workspace Migration Inventory

Captured 2026-09-07 before local directory movement.

| Current repository | Current local path | HEAD | Branch | GitHub | Local status |
|---|---|---|---|---|---|
| `market-data-platform` | `/home/richard/code/market-data-platform` | `7e010c0e2ca5b2ac5e0a59f0badd5fc93f9d3499` | `main` | `runchengxie/market-data-platform` | clean |
| `market-intel` | `/home/richard/code/market-intel` | `692ce08c1da2bb392fb4021ef9e120bb14ca281a` | `main` | `runchengxie/market-intel` | migration docs uncommitted |
| `market-intel-deploy` | `/home/richard/code/market-intel-deploy` | `e2f014aa2c9d948fd654d2be1d42b8004308d4e5` | `main` | `runchengxie/market-intel-deploy` | clean |
| `research-code-quality` | `/home/richard/code/research-code-quality` | `ebe188374d97bb67f832a0f75370624b8ee48c90` | `main` | `runchengxie/research-code-quality` | clean |
| `research-data-maintenance` | `/home/richard/code/research-data-maintenance` | `2e18932b07a1e936ee867f8b5e707a3044007806` | `main` | `runchengxie/research-data-maintenance` | clean |
| `quant-platform` | `/home/richard/code/.public-staging/quant-platform` | `0c16f4b902ba2cc47aaa1e2952c370f9c3a6511e` | `main` | `runchengxie/quant-platform` | clean |
| `quant-research` | `/home/richard/code/.private-staging/quant-research` | `3b9ec98f55ae7796a12bae91432ba352c8384d27` | `main` | `runchengxie/quant-research` | untracked `.worktrees/` directory |

## Target mapping

`market-data-platform` → `quant-market-data-platform`; `quant-platform` → `quant-platform`; `quant-research` → `quant-research`; `market-intel` → `quant-intel-platform`; `market-intel-deploy` → `quant-intel-deploy`; `research-code-quality` → `quant-code-quality`; `research-data-maintenance` → `quant-data-maintenance`.

## Worktree exceptions

- `market-data-platform` has two already-prunable detached worktree records under `/tmp`; they point to missing gitdir locations and must not be deleted as part of this migration.
- `market-intel`, `quant-platform`, and `quant-research` have active linked worktrees under `/home/richard/code/.worktrees`; their registrations must be revalidated after the main worktree moves.
- `quant-research` also contains an untracked `.worktrees/` directory with a linked worktree; it must be preserved.

## Safety decision

The migration docs are committed before any directory or GitHub rename. The existing prunable worktree records are pre-existing exceptions, not migration-created failures. No data roots, credentials, release snapshots, branches, or tags are in scope for deletion.
