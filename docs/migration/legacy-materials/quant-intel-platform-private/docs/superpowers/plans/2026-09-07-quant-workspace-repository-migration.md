# Quant Workspace Repository Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move seven independent quant research repositories to `/home/richard/code` and rename their local directories and GitHub repositories using the approved `quant-` mapping.

**Architecture:** Keep each repository independent. Rename repository identity and source-checkout paths, while preserving Python import names, data-root names, artifact schemas, branches, tags, and release semantics.

**Tech Stack:** Git, GitHub CLI, Python/uv, repository-native pytest/Ruff/type-check commands, shell/PowerShell configuration.

**Spec:** `market-intel/docs/superpowers/specs/2026-09-07-quant-workspace-repository-migration-design.md`

## Global Constraints

- Use the mapping in the spec exactly.
- Do not merge repositories into a monorepo.
- Do not delete worktrees, release checkouts, branches, tags, data, credentials, caches, or outputs.
- Do not rename Python import packages or `DATA_PLATFORM_ROOT` data directories.
- Update every source-repository URL and source-checkout path that becomes stale.
- Preserve and report any intentional legacy names left in schemas, compatibility fixtures, or data paths.

---

### Task 1: Freeze the migration inventory

**Files:**
- Create: `market-intel/docs/superpowers/artifacts/2026-09-07-quant-workspace-migration-inventory.md`

**Interfaces:**
- Consumes: current Git status, remotes, worktree lists, GitHub repository metadata, and repository-reference scan.
- Produces: exact current/target path map, commit SHAs, branch/status snapshot, remote URLs, worktree exceptions, and reference categories.

- [ ] **Step 1: Record each repository's current state**

  Run `git status --short --branch`, `git rev-parse HEAD`, `git remote get-url origin`, and `git worktree list` for all seven repositories.

- [ ] **Step 2: Scan source-controlled and operational references**

  Search tracked files for old GitHub URLs, old source checkout paths, package project names, CI identifiers, and deployment environment names. Exclude `.git`, caches, build output, generated output, and release snapshots from the source scan.

- [ ] **Step 3: Query GitHub metadata**

  Use `gh repo view` for all seven repositories and record owner, visibility, default branch, URL, and repository existence.

- [ ] **Step 4: Write the inventory and commit it**

  Include all command results needed to compare pre- and post-migration state, then commit with `docs: record quant workspace migration inventory`.

### Task 2: Prepare local top-level destinations

**Files:**
- Move: `/home/richard/code/.public-staging/quant-platform` → `/home/richard/code/quant/quant-platform`
- Move: `/home/richard/code/.private-staging/quant-research` → `/home/richard/code/quant/quant-research`
- Move: `/home/richard/code/market-data-platform` → `/home/richard/code/quant/quant-market-data-platform`
- Move: `/home/richard/code/market-intel` → `/home/richard/code/quant/quant-intel-platform`
- Move: `/home/richard/code/market-intel-deploy` → `/home/richard/code/quant/quant-intel-deploy`
- Move: `/home/richard/code/research-code-quality` → `/home/richard/code/quant/quant-code-quality`
- Move: `/home/richard/code/research-data-maintenance` → `/home/richard/code/quant/quant-data-maintenance`

**Interfaces:**
- Consumes: Task 1 inventory and clean-state confirmation.
- Produces: seven top-level Git worktrees with unchanged commits and local Git metadata.

- [ ] **Step 1: Confirm destinations are absent and source repositories are safe to move**

  Abort if any target directory exists, any source repository has tracked or untracked changes other than explicitly recorded migration artifacts, or any source path is the main worktree of a linked-worktree arrangement that Git cannot safely update.

- [ ] **Step 2: Move directories within the same filesystem**

  Use `mv` one repository at a time, preserving directory contents and `.git` metadata. Do not copy-and-delete.

- [ ] **Step 3: Revalidate local Git identity**

  For each target, verify `git rev-parse --show-toplevel`, `git rev-parse HEAD`, `git status --short --branch`, `git remote -v`, and `git worktree list`.

- [ ] **Step 4: Update local worktree registrations if required**

  If Git reports stale administrative paths, use `git worktree repair` from the affected main repository and verify every listed worktree. Do not prune or remove a worktree.

### Task 3: Rename GitHub repositories and remotes

**Files:**
- Modify: each repository's `origin` remote URL

**Interfaces:**
- Consumes: Task 2 local paths and Task 1 GitHub metadata.
- Produces: GitHub repositories with target names and local `origin` URLs matching them.

- [ ] **Step 1: Rename one repository at a time with GitHub CLI**

  Run `gh repo rename <target-name> --repo runchengxie/<current-name> --confirm`, checking the returned URL before proceeding to the next repository.

- [ ] **Step 2: Set the local origin explicitly**

  Run `git remote set-url origin https://github.com/runchengxie/<target-name>.git` in each renamed repository.

- [ ] **Step 3: Verify redirect and target metadata**

  Run `gh repo view runchengxie/<target-name>` and `git ls-remote origin HEAD`; record the new URLs and default branches.

### Task 4: Update repository references and dependency locks

**Files:**
- Modify: tracked README/AGENTS/docs/config files containing source-repository identity or checkout paths
- Modify: `pyproject.toml`, `uv.lock`, manifests, CI workflows, deployment scripts, and test fixtures where they refer to the renamed source repositories

**Interfaces:**
- Consumes: Task 3 target GitHub URLs and target local checkout paths.
- Produces: no stale source-repository URLs or source-checkout paths outside documented legacy compatibility data.

- [ ] **Step 1: Replace GitHub repository URLs**

  Update dependency declarations, lockfile source URLs, badges, workflow repository references, and documentation links. Preserve immutable revisions and package import names.

- [ ] **Step 2: Replace source checkout paths**

  Update paths that mean “the repository checkout,” including `MDP_DIR`, `RESEARCH_WORKSPACE_ROOT`-derived paths, local development examples, and Windows equivalents. Keep `/data/market-data-platform` and related artifact paths unchanged because they are data roots.

- [ ] **Step 3: Update project/repository display names where identity is intended**

  Change project metadata, CI concurrency groups, and deployment config names to target names. Keep schema IDs, artifact names, environment variable names, and Python module names stable unless a test proves they are source-repository identifiers.

- [ ] **Step 4: Regenerate locks using each repository's native command**

  Run `uv lock` or the repository-documented locked dependency update only after manifests are correct, then inspect the diff for unintended version changes.

- [ ] **Step 5: Commit changes per repository**

  Use focused commits such as `chore: update quant repository identities` and record the commit SHAs in the migration artifact.

### Task 5: Run repository and cross-repository verification

**Files:**
- Create: `market-intel/docs/superpowers/artifacts/2026-09-07-quant-workspace-migration-verification.md`

**Interfaces:**
- Consumes: all renamed repositories and updated references.
- Produces: test/quality results, residual-reference classification, final path map, and rollback notes.

- [ ] **Step 1: Verify Git topology**

  Confirm all seven target directories exist directly under `/home/richard/code`, all seven are independent Git repositories, all HEAD SHAs match the pre-migration inventory, and all expected worktrees remain present.

- [ ] **Step 2: Run native checks**

  Run each repository's documented locked test and quality commands, including pytest, Ruff, type checks, and architecture checks where present. Record failures without masking them.

- [ ] **Step 3: Run an old-reference scan**

  Search `/home/richard/code` excluding `.git`, caches, build/output directories, production release snapshots, and intentional compatibility fixtures. Classify every remaining old name as fixed, intentional data/schema vocabulary, or unresolved.

- [ ] **Step 4: Verify downstream package resolution**

  In `quant-intel-deploy`, `quant-platform`, and `quant-research`, verify dependency resolution and locked installs refer to the target repositories or local package sources as designed.

- [ ] **Step 5: Recount code and finalize the report**

  Re-run tracked-file `cloc` for all seven repositories, compare against the pre-migration totals, and commit the verification artifact.

### Task 6: Finalize and provide rollback instructions

**Files:**
- Modify: `market-intel/docs/superpowers/artifacts/2026-09-07-quant-workspace-migration-verification.md`

**Interfaces:**
- Consumes: completed verification evidence.
- Produces: final handoff with target paths, repository URLs, changed commits, known legacy references, and precise rollback steps.

- [ ] **Step 1: Document rollback without destructive commands**

  Explain how to restore each remote URL, how to rename the GitHub repository back if necessary, and how to move local directories back while preserving the recorded commits.

- [ ] **Step 2: Confirm no unresolved migration requirement remains**

  Check every requirement in the design spec and mark the goal complete only after all evidence is present.
