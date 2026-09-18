# Public Framework / Private Deployment Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `market-intel` safe to publish as a public framework and move production-only deployment context into a separately maintained private `market-intel-deploy` repository.

**Architecture:** Keep reusable ETL, scoring, report rendering, artifact validation, generic delivery, CLI, and offline fixtures in `market-intel`. Move customer routing, credentials, production paths, schedulers, recovery bridges, real snapshots, and private runbooks to `market-intel-deploy`; the private repository installs a pinned public release and never becomes a dependency of public code.

**Tech Stack:** Python 3.11–3.13, uv, setuptools, pytest, Ruff, ty, GitHub Actions, shell/systemd/PowerShell deployment assets, versioned JSON/Parquet artifact contracts.

**Spec:** `docs/superpowers/specs/2026-09-05-public-framework-private-deployment-design.md`

## Global Constraints

- Public CI must pass without secrets, private repositories, private network access, production filesystem paths, or real customer data.
- Public code must communicate with research/data owners only through public CLI commands and versioned artifacts.
- Production must pin an immutable public release; it must not install `market-intel` from `main`.
- Public configuration uses semantic audiences such as `client` and `internal`; customer-specific names remain private compatibility aliases only.
- Real production state, output, snapshots, receipts, logs, credentials, and internal endpoints must not enter the public repository or its history.
- Every behavior change follows a failing-test-first cycle; configuration-only moves are validated with repository and workflow checks.
- Do not change repository visibility until the clean-history export and full-history scan in Task 8 pass.

---

### Task 1: Build the file-level migration manifest and baseline scans

**Files:**
- Create: `docs/public-release/file-migration-manifest.yml`
- Create: `docs/public-release/public-release-checklist.md`
- Test: `tests/public_release/test_file_migration_manifest.py`

**Interfaces:**
- Consumes: tracked files from `git ls-files`, the public/private boundary in the spec, and current GitHub workflow files.
- Produces: a machine-readable classification for every tracked file and a checklist used by later tasks and the final clean-history export.

- [ ] **Step 1: Write the failing manifest coverage test**

```python
from pathlib import Path

import yaml


def test_manifest_classifies_every_tracked_file():
    root = Path(__file__).parents[2]
    manifest = yaml.safe_load((root / "docs/public-release/file-migration-manifest.yml").read_text())
    tracked = set(__import__("subprocess").check_output(["git", "ls-files"], text=True).splitlines())
    classified = {entry["path"] for entry in manifest["files"]}
    assert tracked <= classified
    assert {entry["classification"] for entry in manifest["files"]} <= {
        "public",
        "private",
        "split",
        "remove",
    }
```

- [ ] **Step 2: Run the test and verify it fails because the manifest does not exist**

Run: `uv run pytest tests/public_release/test_file_migration_manifest.py -q`

Expected: FAIL with a missing-file error for `docs/public-release/file-migration-manifest.yml`.

- [ ] **Step 3: Add the initial manifest**

Classify all current tracked paths. At minimum, classify `src/` packages, `tests/`, `config/`, `data-snapshots/`, `state/`, `out/`, `scripts/`, `.github/workflows/`, `docs/`, `.env.example`, `api_keys.json.example`, and `pyproject.toml`. Use `split` for files needing sanitization and `private` for production schedules, customer routing, real snapshots, and host-specific deployment.

Use this shape:

```yaml
version: 1
files:
  - path: src/daily_messenger/scoring/run_scores.py
    classification: public
    action: retain
    reason: generic scoring implementation
  - path: scripts/systemd/daily-watch20-producer.service
    classification: private
    action: move
    reason: production scheduler and filesystem topology
```

- [ ] **Step 4: Add the release checklist**

Include checkboxes for tree scan, history scan, dependency visibility, data rights, audience sanitization, CI without secrets, private deployment smoke test, clean export, and final visibility change.

- [ ] **Step 5: Run the test and commit**

Run: `uv run pytest tests/public_release/test_file_migration_manifest.py -q`

Expected: PASS with every tracked file classified.

Commit:

```bash
git add docs/public-release tests/public_release/test_file_migration_manifest.py
git commit -m "docs: add public release migration manifest"
```

### Task 2: Define the public audience and delivery contract

**Files:**
- Create: `src/market_intel_config/audiences.py`
- Modify: `src/a_share_daily/delivery/targets.py`
- Modify: `src/a_share_daily/delivery/report_delivery.py`
- Modify: `src/a_share_daily/daily_watch20_lark_delivery.py`
- Test: `tests/a_share_daily/test_public_audience_contract.py`
- Test: `tests/a_share_daily/test_delivery_targets.py`

**Interfaces:**
- Consumes: existing delivery target resolution and sender APIs.
- Produces: `Audience = Literal["client", "internal", "public"]`, `resolve_audience_targets(audience: str) -> tuple[str, ...]`, and a public-safe default that returns no destination when no injected destination is configured.

- [ ] **Step 1: Write failing tests for generic audience resolution**

```python
def test_client_audience_uses_generic_environment_variable(monkeypatch):
    monkeypatch.setenv("MARKET_INTEL_CLIENT_CHAT_ID", "oc_client")
    assert resolve_audience_targets("client") == ("oc_client",)


def test_public_audience_has_no_default_destination(monkeypatch):
    monkeypatch.delenv("MARKET_INTEL_CLIENT_CHAT_ID", raising=False)
    monkeypatch.delenv("MARKET_INTEL_INTERNAL_CHAT_ID", raising=False)
    assert resolve_audience_targets("public") == ()


def test_unknown_audience_fails_closed():
    with pytest.raises(ValueError, match="unknown audience"):
        resolve_audience_targets("customer-name")
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `uv run pytest tests/a_share_daily/test_public_audience_contract.py -q`

Expected: FAIL because `resolve_audience_targets` and the generic audience module do not exist.

- [ ] **Step 3: Implement the minimum public audience contract**

Read only `MARKET_INTEL_CLIENT_CHAT_ID`, `MARKET_INTEL_INTERNAL_CHAT_ID`, and `MARKET_INTEL_PUBLIC_CHAT_ID` in the public resolver. Do not read or mention customer-specific aliases in the public implementation. Preserve the existing sender protocol by returning destination strings to the existing delivery layer.

- [ ] **Step 4: Update delivery callers and remove customer semantics from public behavior**

Change delivery call sites that currently call `_audience_chat_id("kaichuan")` to call `resolve_audience_targets("client")`. Change result keys such as `kaichuan_enabled` to `client_enabled`. Keep any compatibility mapping in a later private deployment adapter, not in public source.

- [ ] **Step 5: Run focused and existing delivery tests**

Run: `uv run pytest tests/a_share_daily/test_public_audience_contract.py tests/a_share_daily/test_delivery_targets.py -q`

Expected: PASS with no customer-specific environment variable required.

- [ ] **Step 6: Run the public source scan and commit**

Run: `rg -n -i 'kaichuan|凯川|A_SHARE_KAICHUAN' src tests docs README.md`

Expected: no matches in public source, tests, README, or public docs after the task's related documentation changes.

Commit:

```bash
git add src/market_intel_config src/a_share_daily/delivery src/a_share_daily/daily_watch20_lark_delivery.py tests/a_share_daily
git commit -m "refactor: make delivery audiences public-safe"
```

### Task 3: Remove implicit production path defaults from public runtime code

**Files:**
- Modify: `src/a_share_daily/daily_watch20.py`
- Modify: `src/a_share_daily/daily_watch20_raw_completeness.py`
- Modify: `src/a_share_daily/tushare_credentials.py`
- Modify: `src/ops_common/env.py`
- Modify: `scripts/refresh_a_share_index_daily.py`
- Modify: `scripts/check_index_daily_freshness.py`
- Modify: `scripts/check_daily_watch20_producer_freshness.py`
- Test: `tests/ops_common/test_explicit_external_roots.py`

**Interfaces:**
- Consumes: existing `DATA_PLATFORM_ROOT`, `MDP_DIR`, `STRATEGY_PIPELINE_ROOT`, and `MDP_FALLBACK_ROOT` environment variables.
- Produces: explicit root resolution that raises a clear configuration error instead of silently using `$HOME/data/market-data-platform` or `$HOME/code/research-workspace`.

- [ ] **Step 1: Write failing tests for missing-root behavior**

```python
def test_data_platform_root_is_required_when_external_data_is_requested(monkeypatch):
    monkeypatch.delenv("DATA_PLATFORM_ROOT", raising=False)
    monkeypatch.delenv("MDP_FALLBACK_ROOT", raising=False)
    with pytest.raises(RuntimeError, match="DATA_PLATFORM_ROOT"):
        resolve_data_platform_root(required=True)


def test_explicit_root_is_used(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_PLATFORM_ROOT", str(tmp_path))
    assert resolve_data_platform_root(required=True) == tmp_path
```

- [ ] **Step 2: Run the tests and verify the expected failure**

Run: `uv run pytest tests/ops_common/test_explicit_external_roots.py -q`

Expected: FAIL because the resolver still has implicit path fallbacks or the tested helper is not yet present.

- [ ] **Step 3: Implement explicit root resolution**

Centralize the behavior in `ops_common.env` and update callers to use it. Preserve `MDP_FALLBACK_ROOT` only as an explicitly configured compatibility escape hatch. Do not add a new `$HOME` fallback.

- [ ] **Step 4: Update shell and Python bridges**

Change scripts to require the relevant environment variable before accessing external data. Keep public code capable of running offline with fixtures; production-only bridge scripts will be moved in Task 6.

- [ ] **Step 5: Run focused tests, boundary scans, and commit**

Run:

```bash
uv run pytest tests/ops_common/test_explicit_external_roots.py -q
rg -n 'Path\.home\(\).*market-data-platform|\$HOME/data/market-data-platform|\$HOME/code/research-workspace' src scripts
```

Expected: focused tests PASS; remaining matches are explicitly classified for private migration, not public runtime defaults.

Commit:

```bash
git add src/ops_common src/a_share_daily scripts tests/ops_common
git commit -m "refactor: require explicit external data roots"
```

### Task 4: Replace real snapshots and production state with public fixtures

**Files:**
- Modify: `.gitignore`
- Modify: `data-snapshots/latest/tushare_snapshot.json`
- Modify: `data-snapshots/latest/cross_market_snapshot.json`
- Modify: `data-snapshots/latest/cross_market_snapshot.md`
- Create: `tests/fixtures/public/cross_market_snapshot.json`
- Create: `tests/fixtures/public/tushare_snapshot.json`
- Create: `docs/public-release/data-provenance.md`
- Test: `tests/public_release/test_public_fixture_policy.py`

**Interfaces:**
- Consumes: existing snapshot readers and dashboard/report fixture loaders.
- Produces: small synthetic fixtures that preserve schema but contain no real production observations, proxy labels, customer identifiers, or internal URLs.

- [ ] **Step 1: Write the failing fixture policy test**

```python
def test_public_fixtures_contain_no_private_markers():
    root = Path(__file__).parents[2]
    text = "\n".join(path.read_text() for path in (root / "tests/fixtures/public").rglob("*"))
    for marker in ("fast.xiaodefa.cn", "feishu.cn", "凯川", "kaichuan", "token_label"):
        assert marker.lower() not in text.lower()


def test_public_snapshot_files_are_small():
    root = Path(__file__).parents[2]
    assert all(path.stat().st_size < 100_000 for path in (root / "tests/fixtures/public").rglob("*"))
```

- [ ] **Step 2: Run the test and verify it fails against missing public fixtures**

Run: `uv run pytest tests/public_release/test_public_fixture_policy.py -q`

Expected: FAIL because the public fixture directory does not yet exist.

- [ ] **Step 3: Create schema-compatible synthetic fixtures**

Copy only the minimum fields required by offline readers, replace dates and values with deterministic examples, remove provider proxy metadata, and document that the fixtures are synthetic. Do not copy the current production snapshot wholesale.

- [ ] **Step 4: Remove real snapshot content from the public tree**

Replace tracked production snapshot files with `.gitkeep` or documented synthetic examples. Keep `state/` and `out/` ignored and empty in the public repository.

- [ ] **Step 5: Run fixture and dashboard/report tests**

Run:

```bash
uv run pytest tests/public_release/test_public_fixture_policy.py tests/test_web_dashboard.py tests/test_digest.py -q
```

Expected: PASS, with any test path adjustments made only to point at synthetic fixtures.

- [ ] **Step 6: Commit the fixture policy**

```bash
git add .gitignore data-snapshots tests/fixtures/public docs/public-release tests/public_release/test_public_fixture_policy.py
git commit -m "chore: replace production snapshots with public fixtures"
```

### Task 5: Split public and private documentation and update package metadata

**Files:**
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/operations.md`
- Modify: `docs/report-distribution.md`
- Modify: `docs/new-machine-setup.md`
- Modify: `docs/boundary-contract.md`
- Modify: `pyproject.toml`
- Create: `docs/public-release/README.md`
- Create: `docs/public-release/private-migration-notes.md`
- Test: `tests/public_release/test_public_docs.py`

**Interfaces:**
- Consumes: current README navigation, package metadata, and cross-repository contract documentation.
- Produces: public documentation with no private topology and an explicit private migration note listing content that must move to `market-intel-deploy`.

- [ ] **Step 1: Write the failing public documentation scan**

```python
def test_public_docs_have_no_private_markers():
    root = Path(__file__).parents[2]
    files = [root / "README.md", *(root / "docs").glob("*.md")]
    text = "\n".join(path.read_text() for path in files if path.exists())
    for marker in ("凯川", "kaichuan", "fast.xiaodefa.cn", "my.feishu.cn/docx/"):
        assert marker.lower() not in text.lower()
```

- [ ] **Step 2: Run the test and verify the expected failure**

Run: `uv run pytest tests/public_release/test_public_docs.py -q`

Expected: FAIL because current operational and distribution docs contain private markers or production topology.

- [ ] **Step 3: Rewrite public docs**

Keep generic architecture, artifact contracts, failure semantics, local development, and offline testing. Replace customer names with semantic audiences, replace real URLs with interface descriptions, and state that production deployment is maintained separately.

- [ ] **Step 4: Move private material into the migration notes**

Record the exact source documents and sections to move to `market-intel-deploy`, without copying their sensitive values into the public file. The private repository will receive the actual content during Task 6.

- [ ] **Step 5: Make dependency visibility explicit**

Confirm whether the pinned `research-contracts` Git dependency is public and installable. If it is not, change `pyproject.toml` in the implementation to a public package/release or a public contracts repository before public CI is enabled. Do not silently leave a private dependency in place.

- [ ] **Step 6: Run documentation and package checks and commit**

Run:

```bash
uv run pytest tests/public_release/test_public_docs.py -q
uv lock --check
uv build
```

Expected: documentation scan PASS, lock metadata valid, and both distributions build without private access.

Commit:

```bash
git add README.md docs pyproject.toml tests/public_release/test_public_docs.py
git commit -m "docs: publish safe framework boundary"
```

### Task 6: Create the private deployment repository skeleton and move production assets

**Files:**
- Create in private repository: `market-intel-deploy/README.md`
- Create in private repository: `market-intel-deploy/pyproject.toml`
- Create in private repository: `market-intel-deploy/config/production.yml`
- Create in private repository: `market-intel-deploy/deploy/systemd/`
- Create in private repository: `market-intel-deploy/deploy/windows/`
- Create in private repository: `market-intel-deploy/scripts/`
- Create in private repository: `market-intel-deploy/runbooks/`
- Create in private repository: `market-intel-deploy/manifests/market-intel.lock`
- Modify in public repository: `docs/public-release/private-migration-notes.md`

**Interfaces:**
- Consumes: the public CLI contracts, generic audience configuration, explicit external roots, and versioned artifact contracts produced by Tasks 2–5.
- Produces: a private deployment project that installs a pinned public version and owns all production-only entry points.

- [ ] **Step 1: Add a private repository README and lock manifest**

Document the one-way dependency and pin the first public release by tag or immutable commit. The deployment package must not import public repository source by filesystem path.

- [ ] **Step 2: Move production configuration and compatibility aliases**

Put actual audience mappings, environment-variable compatibility aliases, provider settings, and host-specific paths in `config/production.yml` or deployment environment files. Keep secrets in the host secret manager or environment, not Git.

- [ ] **Step 3: Move production bridges and schedulers**

Move `scripts/systemd/`, `scripts/windows/`, `scripts/setup_cron.sh`, and production bridges such as `scripts/refresh_daily_watch20.sh`, `scripts/daily_watch20_delivery.sh`, `scripts/morning_product_supervisor.sh`, and recovery scripts. Adapt them to invoke installed public CLIs and owner CLIs using explicit environment variables.

- [ ] **Step 4: Add private integration checks**

Add tests that validate configuration shape, public version compatibility, artifact receipt compatibility, deployment manifest syntax, and delivery dry-run behavior. Live sending remains an explicitly invoked smoke test, not a default CI action.

- [ ] **Step 5: Run private validation and update the migration notes**

Run the private repository's unit/contract checks and a no-send production dry run. Record the final moved-file mapping in `docs/public-release/private-migration-notes.md` without adding private values to the public repository.

### Task 7: Add secret-free public CI and repository boundary checks

**Files:**
- Modify: `.github/workflows/pr-light.yml`
- Create: `.github/workflows/public-quality.yml`
- Create: `scripts/public_release/check_boundary.py`
- Test: `tests/public_release/test_boundary_checker.py`

**Interfaces:**
- Consumes: the public fixture policy, documentation policy, file manifest, package build, and existing quality commands.
- Produces: a GitHub Actions matrix that runs without repository secrets and fails on newly introduced private markers or production defaults.

- [ ] **Step 1: Write failing boundary checker tests**

```python
def test_boundary_checker_rejects_private_marker(tmp_path):
    (tmp_path / "README.md").write_text("internal endpoint: https://fast.xiaodefa.cn")
    result = check_tree(tmp_path)
    assert "fast.xiaodefa.cn" in result.forbidden_matches


def test_boundary_checker_accepts_generic_example(tmp_path):
    (tmp_path / "README.md").write_text("MARKET_INTEL_CLIENT_CHAT_ID=example")
    result = check_tree(tmp_path)
    assert result.forbidden_matches == ()
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `uv run pytest tests/public_release/test_boundary_checker.py -q`

Expected: FAIL because `check_tree` does not exist.

- [ ] **Step 3: Implement the boundary checker**

Scan tracked text files only. Reject customer names, private endpoint patterns, real Feishu document URLs, common credential formats, production home-directory defaults, and private repository names. Allow explicit generic placeholders and allow the private migration notes to refer to source paths without copying private values.

- [ ] **Step 4: Add public workflow jobs**

Configure `public-quality.yml` to run on pull requests and pushes with Python 3.11, 3.12, and 3.13 on Ubuntu. Run `uv sync --locked --group dev`, boundary check, Ruff lint, Ruff format check, ty, pytest, CLI help checks, and package build. Do not configure secrets, data fetches, Feishu calls, or automatic commits.

- [ ] **Step 5: Run the workflow-equivalent commands locally**

Run:

```bash
uv run python scripts/public_release/check_boundary.py
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest
uv build
```

Expected: every command exits 0 in an environment with no production variables configured.

- [ ] **Step 6: Commit the public CI gate**

```bash
git add .github/workflows scripts/public_release tests/public_release/test_boundary_checker.py
git commit -m "ci: add secret-free public quality gate"
```

### Task 8: Produce a clean public history and final release audit

**Files:**
- Create outside the working repository: `/home/richard/code/market-intel-public-export/`
- Create in export: sanitized Git history and public repository tree
- Update: `docs/public-release/public-release-checklist.md`

**Interfaces:**
- Consumes: the complete public-safe tree, file migration manifest, boundary checker, package build, and private deployment smoke-test evidence.
- Produces: a clean export ready for a separate public GitHub repository; it does not change GitHub visibility of the existing private repository.

- [ ] **Step 1: Run current-tree and full-history scans**

Run:

```bash
git grep -n -I -i -E 'api[_-]?key|secret|token|private[_-]?key|feishu\.cn|fast\.xiaodefa\.cn|kaichuan|凯川|chat[_-]?id|/home/[^ ]*market-data-platform' $(git rev-list --all) -- ':!docs/public-release/private-migration-notes.md'
```

Also run an approved secret scanner such as `gitleaks git --redact --verbose` against the full repository history. Record findings and dispositions in the private release checklist, not in public documentation if the finding contains sensitive values.

- [ ] **Step 2: Build the clean export**

Create a new export containing only files classified `public` or sanitized `split`. Do not use `git filter-branch` on the working repository. Preserve file modes and package metadata, but initialize a new Git history for the public repository.

- [ ] **Step 3: Verify the export independently**

From the export directory, run:

```bash
uv sync --locked --group dev
uv run python scripts/public_release/check_boundary.py
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest
uv build
```

Expected: all commands pass without credentials, private paths, adjacent repositories, or private network access.

- [ ] **Step 4: Verify the private deployment against a pinned public release**

Install the public release into `market-intel-deploy`, run configuration validation, artifact contract tests, schedule manifest checks, and delivery dry-run tests. Do not make a live delivery part of the default release gate.

- [ ] **Step 5: Complete the visibility-change checklist**

Confirm data redistribution rights, license, dependency visibility, GitHub Actions permissions, branch protection, issue templates, security policy, and absence of real production state. Only after all checklist items are checked may an owner create the public GitHub repository and push the clean export.

- [ ] **Step 6: Commit the final audit documentation to the private deployment repository**

Keep the detailed audit results and any sensitive finding disposition in the private repository. The public repository receives only the sanitized release checklist and general contribution guidance.

## Verification matrix

| Milestone | Required evidence |
|---|---|
| Public boundary | `test_public_audience_contract.py`, `test_explicit_external_roots.py`, and boundary checker pass |
| Public data policy | Fixture policy passes and no real snapshot remains in the public export |
| Documentation safety | Public documentation scan passes with no private markers |
| Package usability | `uv lock --check` and `uv build` pass without private access |
| Public CI | Workflow-equivalent local commands pass with production variables unset |
| Private deployment | Pinned-release integration and dry-run delivery checks pass |
| Final publication | Full-history secret scan, clean export audit, and legal/data-rights checklist are complete |

## Execution order and stopping points

Tasks 1–5 are the public-safe framework migration and can be reviewed independently. Task 6 creates the private deployment boundary and should not begin until Tasks 2–5 have passed. Task 7 may run alongside Task 6 after the public APIs stabilize. Task 8 is the final publication gate and must not be skipped or collapsed into an ordinary code review.
