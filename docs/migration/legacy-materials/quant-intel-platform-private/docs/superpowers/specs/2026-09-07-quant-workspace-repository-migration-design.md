# Quant Workspace Repository Migration Design

## Goal

将量化投研相关的 7 个独立 Git 仓库统一放到 `/home/richard/code` 顶层，并用统一的 `quant-` 命名空间增强关联性，同时保持仓库、权限、发布和职责边界不变。

## Repository mapping

| Current | Target local directory | Target GitHub repository |
|---|---|---|
| `market-data-platform` | `quant-market-data-platform` | `quant-market-data-platform` |
| `quant-platform` | `quant-platform` | `quant-platform` |
| `quant-research` | `quant-research` | `quant-research` |
| `market-intel` | `quant-intel-platform` | `quant-intel-platform` |
| `market-intel-deploy` | `quant-intel-deploy` | `quant-intel-deploy` |
| `research-code-quality` | `quant-code-quality` | `quant-code-quality` |
| `research-data-maintenance` | `quant-data-maintenance` | `quant-data-maintenance` |

Python import package names are not renamed in this migration. Runtime data roots such as `DATA_PLATFORM_ROOT` are also not renamed; they identify data storage, not source repositories.

## Boundaries and safety

- The seven repositories remain separate Git repositories.
- Existing branches, commits, tags, GitHub visibility, and working-tree changes are preserved.
- Before each remote rename, the old remote URL and repository mapping are recorded.
- Local directory moves happen only after worktree and dirty-state checks.
- Existing GitHub redirects are not treated as a substitute for updating dependency manifests, lockfiles, CI, docs, and deployment configuration.
- Active worktrees and release checkouts are not moved or deleted automatically; they are audited and handled explicitly.

## Dependency and path policy

Update repository identity references such as GitHub URLs, package project names, CI concurrency groups, deployment manifests, and documentation. Preserve domain vocabulary inside data paths, schema names, artifact names, and compatibility fixtures unless changing it is required to refer to the source repository. Cross-repository integration continues to use published packages, public CLIs, environment variables, and versioned artifacts.

## Verification

For every repository, verify the new location is a clean Git worktree on the same commit, `origin` points to the new GitHub URL, and repository-specific tests/quality gates pass. Globally scan for old repository URLs and old source checkout paths, then verify expected compatibility names are either intentional or documented.
