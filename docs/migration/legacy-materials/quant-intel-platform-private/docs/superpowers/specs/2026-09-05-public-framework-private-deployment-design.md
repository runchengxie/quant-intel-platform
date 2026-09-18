# Public Framework / Private Deployment Design

**Date:** 2026-09-05  
**Status:** Approved design draft  
**Scope:** Repository boundary and migration design for `market-intel`

## Goal

Refactor `market-intel` so that it can be published as a public framework without exposing customer identity, production delivery topology, credentials, private infrastructure, operational runbooks, or real production data, while keeping production behavior available through a separate private `market-intel-deploy` repository.

The public repository must be independently testable and able to run its complete quality gate without secrets, private repositories, private network access, production filesystem paths, or real customer data.

## Context and current state

`market-intel` already has a useful cross-repository boundary: research and data owners expose public CLI commands and versioned artifacts, while this repository validates, renders, delivers, and recovers reports. `AGENTS.md`, `README.md`, and `docs/boundary-contract.md` already prohibit importing research implementation or treating adjacent repository paths as APIs.

The repository is not yet a pure public framework. It currently mixes:

- reusable ETL, scoring, report rendering, dashboard, artifact validation, and delivery code;
- production audience routing and compatibility aliases;
- systemd, Windows, cron, and recovery scripts;
- real-data snapshot and production-path assumptions;
- operational documentation and deployment instructions;
- a dependency on a Git revision in `research-workspace` that must be verified as consumable by a public repository.

The refactor should preserve the existing artifact-first cross-repository model rather than introduce imports from a private deployment repository into public code.

## Decision

Use two repositories with a one-way dependency:

```text
market-intel              public framework
        ▲
        │ pinned release / package dependency
market-intel-deploy       private production deployment
```

`market-intel` remains responsible for domain behavior that is generic, reproducible, and testable with synthetic fixtures. `market-intel-deploy` becomes responsible for real-world deployment context and production policy.

The public repository must never depend on, checkout, import, or invoke private deployment code. The private repository may install a pinned release of the public repository and supply configuration, paths, schedules, credentials, and production-only adapters.

## Public repository boundary

### Public responsibilities

The public repository owns:

- global market ETL interfaces and source-specific fetchers that can run with supplied credentials or deterministic fallback fixtures;
- scoring, technical-analysis, report assembly, rendering, and dashboard generation;
- A-share report-side interpretation and validation of published owner artifacts;
- artifact, receipt, freshness, and schema validation contracts;
- generic delivery interfaces and transport implementations that do not contain real destinations;
- generic audience names such as `client`, `internal`, and `public`;
- CLI contracts: `dm`, `marketops`, and `a-share-daily`;
- synthetic, minimized, or clearly redistributable test fixtures;
- offline unit tests, contract tests, rendering snapshots, static checks, and package builds;
- public architecture, contributor, testing, and contract documentation.

### Private responsibilities

`market-intel-deploy` owns:

- real customer and partner names;
- real Feishu chat IDs, user IDs, webhooks, and routing matrices;
- production secrets and credential files;
- production schedules, systemd units, Windows scheduled tasks, and cron installation;
- actual filesystem roots, data lake paths, service accounts, and host-specific environment files;
- production recovery procedures and escalation details;
- private proxy or data-provider endpoints;
- real production snapshots, receipts, logs, and state;
- private repository checkout details and deployment-only compatibility shims;
- end-to-end production smoke tests and live delivery checks.

### Public safety invariants

Every public pull request and push must satisfy these invariants:

1. No secret is required for CI to pass.
2. No private repository is required for CI to pass.
3. No production filesystem path is required for CI to pass.
4. No private network or internal endpoint is required for CI to pass.
5. No real customer or partner data is used by tests or fixtures.
6. No real production snapshot is distributed by the public repository.
7. Public documentation describes interfaces and capabilities, not private topology.

## Target repository layout

### `market-intel` public

```text
market-intel/
  src/
    daily_messenger/        # generic market/news ETL, scoring, digest, dashboard, TA
    a_share_daily/           # report assembly, artifact validation, rendering, generic delivery
    a_share_analysis/        # report-side consumption of published research artifacts
    tushare_jobs/            # only report-owned lightweight/compatibility exports
    style_replica_bridge/    # owner artifact to report tearsheet adapter
    ops_common/              # generic environment, windows, freshness, receipt helpers
    market_intel_config/     # public-safe configuration schemas/defaults
  config/
    examples and generic defaults only
  tests/
    unit, contract, rendering, and synthetic integration fixtures
  docs/
    public architecture, contracts, local development, and contribution guidance
  .github/workflows/
    secret-free quality and package workflows
```

The public repository must not contain real `state/`, `out/`, production `data-snapshots/`, deployment environment files, or host-specific scheduler definitions.

### `market-intel-deploy` private

```text
market-intel-deploy/
  config/
    production audience and delivery mappings
    host and provider settings
  deploy/
    systemd/
    windows/
    cron/
  scripts/
    production bridges and recovery entry points
  runbooks/
    internal operations, escalation, and restoration procedures
  smoke_tests/
    private integration checks against pinned public release
  manifests/
    public framework version and artifact compatibility locks
```

Production data, state, receipts, logs, and credentials remain outside Git unless there is an explicitly reviewed storage policy.

## Configuration and audience contract

The public layer must use semantic audience names and transport interfaces. It must not encode customer names in environment variables, function names, documentation, or default routing logic.

Public configuration should express a contract such as:

```yaml
audiences:
  client:
    transport: feishu
  internal:
    transport: feishu
```

Private deployment configuration maps those semantic audiences to actual destinations:

```yaml
audiences:
  client:
    chat_id_env: MARKET_INTEL_CLIENT_CHAT_ID
  internal:
    chat_id_env: MARKET_INTEL_INTERNAL_CHAT_ID
```

The public CLI may accept an injected configuration path or environment variables, but public defaults must be safe and non-delivering. A local run without destinations must render or validate artifacts without attempting to contact a real target.

Existing customer-specific names such as `kaichuan` and `A_SHARE_KAICHUAN_*` are migration liabilities. They should be retained only in the private repository as compatibility aliases until production has moved to generic audience names.

## Artifact and version contract

The public framework consumes research and data outputs through versioned CLI and file contracts. It must not import business source from `research-workspace` or any private deployment repository.

The private repository pins the public framework to an immutable release or commit. The preferred progression is:

```text
public change
  → public CI
  → tagged release
  → private dependency update
  → private contract/smoke checks
  → production rollout
```

Direct dependency on the public `main` branch is not allowed for production. The current `research-contracts` Git dependency must be checked during implementation: it must either remain consumable from a public repository, move to a public package/release, or be replaced by a separately versioned public contract package. A public CI job must never rely on a private checkout of `research-workspace`.

## CI design

### Public CI

The public repository should run a broad secret-free matrix, including as applicable:

- supported Python versions;
- Linux and any additional supported operating systems;
- formatting and lint checks;
- type checks with public-safe dependency resolution;
- unit and contract tests;
- rendering and snapshot tests using synthetic fixtures;
- CLI help and package build checks;
- a repository boundary scan that rejects private destinations, credentials, real customer names, and production paths.

The public workflows must not fetch real market data, call Feishu, publish production artifacts, or commit generated snapshots.

### Private CI

The private repository should run a smaller integration-focused gate:

- validate private configuration shape and required secrets;
- install the pinned public release;
- validate artifact compatibility with deployed owner versions;
- verify production filesystem and external CLI availability;
- run delivery and recovery smoke tests where safe;
- verify schedule/deployment manifests.

Private CI must not duplicate the public unit-test matrix.

## Documentation split

Move or rewrite documentation according to information sensitivity:

### Keep public, after sanitization

- `docs/architecture.md`: generic pipeline and dependency direction;
- `docs/boundary-contract.md`: public CLI/artifact boundary;
- `docs/contracts.md`: schema and receipt contracts without private paths;
- `docs/testing.md`: secret-free local and CI testing;
- `docs/report-structure.md`, `docs/web-dashboard.md`, `docs/scoring.md`, and `docs/ta-methodology.md`: only if the level of methodology disclosure is intentional;
- public setup and contributor documentation.

### Split or move private

- `docs/report-distribution.md`: customer names, audiences, schedules, and routing matrix;
- `docs/new-machine-setup.md`: host paths, private repositories, and machine-specific deployment;
- `docs/operations.md`: retain public failure semantics, move escalation and production recovery details;
- schedule and deployment instructions containing systemd, Windows, cron, or production paths;
- proxy/provider topology and internal handoff notes.

The public README should explain how to run offline with synthetic or user-supplied inputs, and should link to contracts rather than describe private production operations.

## Data policy

The public repository may include only:

- synthetic fixtures;
- small samples whose redistribution rights are confirmed;
- public static assets intentionally published as examples;
- schema examples with anonymized identifiers.

The following must be removed from the public history and current tree before visibility changes:

- real TuShare or other provider snapshots unless redistribution is explicitly approved;
- production `state/` and `out/` content;
- proxy labels and internal endpoint identifiers;
- customer-specific receipts, reports, logs, or delivery records.

Because Git history is part of public visibility, the final public repository should be created from a clean sanitized history or a clean export after the migration. A current-tree cleanup alone is insufficient.

## Migration phases

### Phase 0: inventory and release gate

- classify every tracked file as public, private, split, or delete;
- scan current tree and full Git history for secrets, customer identifiers, internal URLs, proxy endpoints, real data, and private repository references;
- verify the public dependency graph, especially `research-contracts`;
- decide which methodology and strategy details are intentionally public;
- define the first public release and compatibility policy.

Deliverable: a reviewed file-level migration manifest and a public release checklist.

### Phase 1: make the framework public-safe in place

- replace customer-specific audience concepts with generic audience contracts;
- remove production-path fallbacks from public Python and shell entry points;
- separate generic delivery interfaces from destination resolution;
- replace real snapshots with synthetic fixtures;
- split public and private documentation;
- add secret-free boundary checks and complete public CI;
- update package/dependency resolution so public CI works without private repositories.

Deliverable: the current repository passes the public safety invariants while production remains operational through temporary compatibility configuration.

### Phase 2: create `market-intel-deploy`

- create the private repository with deployment manifests, production scripts, routing configuration, and private runbooks;
- move systemd, Windows, cron, recovery, and production bridge scripts;
- move actual audience mappings and secret names;
- add a lockfile or manifest for the public framework release;
- add private integration and delivery smoke tests.

Deliverable: production can be exercised from the private repository against a pinned public release.

### Phase 3: cut over production

- deploy the private repository using the same stable production checkout policy;
- run parallel or shadow validation for report rendering, artifact consumption, delivery, freshness, and recovery;
- update schedules to call private deployment entry points;
- remove temporary compatibility aliases from public code after an agreed deprecation window;
- archive or quarantine sensitive history before making the public repository visible.

Deliverable: public framework and private deployment are independently maintainable with a one-way dependency.

## Rollback strategy

Rollback must be possible without changing public repository visibility again:

- keep the current private production repository and pinned release until the cutover is validated;
- make deployment selection switchable by public framework version;
- retain previous deployment manifests and artifact compatibility locks;
- if a public release is incompatible, pin the prior release in private deployment and fix forward;
- do not restore production secrets or customer data into the public repository as a rollback mechanism.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| A secret or customer identifier survives in Git history | Clean export/new public history plus full-history secret and identifier scan before visibility change |
| Public CI still resolves a private dependency | Publish/version the contracts package or make the dependency explicitly public before release |
| Production behavior changes during audience abstraction | Keep private compatibility aliases and run delivery smoke tests before removing them |
| Public code silently assumes a production path | Reject implicit path defaults and require explicit environment/config injection |
| Real snapshots are redistributed without permission | Replace with synthetic fixtures and document data provenance/rights |
| Private CI duplicates public checks | Keep private CI integration-only and pin public release artifacts |
| Public methodology disclosure is broader than intended | Review strategy and methodology docs separately from software boundary review |

## Success criteria

The design is considered implemented when:

1. `market-intel` can be made public from a sanitized history without exposing customer identity, production routing, credentials, internal endpoints, real production data, or private repository topology.
2. Public CI passes without secrets, private repositories, private network access, or production filesystem paths.
3. `market-intel-deploy` can install a pinned public release and run production integration checks.
4. Public code depends only on public CLI and versioned artifact contracts for cross-repository research/data behavior.
5. Production schedules, credentials, recipients, data paths, recovery policy, and private runbooks are maintained only in the private repository or deployment environment.
6. A release, rollback, and deprecation workflow is documented and testable.

