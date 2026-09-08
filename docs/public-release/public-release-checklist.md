# Public Release Checklist

Use this checklist before creating or updating the public GitHub repository. The existing private repository must remain the source of production history until every item is complete.

## Cutover evidence

Record these values in the private deploy repository before publication:

- `source_revision`: final reviewed revision in the private source checkout;
- `public_revision`: commit at the root of the clean public export;
- `public_release_tag`: first immutable public release tag;
- `deploy_platform_pin`: active deploy dependency resolved to a 40-character commit;
- `rollback_platform_pin`: previous known-good deploy dependency resolved to a 40-character commit.

## Boundary

- [ ] Every tracked file is classified in `file-migration-manifest.yml`.
- [ ] Public source uses semantic audiences only.
- [ ] Production schedules, recovery bridges, and host-specific deployment files are private.
- [ ] Public code does not import, checkout, or depend on private deployment code.
- [ ] Public code does not use implicit production filesystem defaults.

## Data and privacy

- [ ] No real customer, partner, group, user, or internal document identifier remains in the public tree.
- [ ] No real webhook, chat ID, token, credential, private endpoint, or proxy label remains in the public tree.
- [ ] Real production `state/`, `out/`, receipts, logs, and provider snapshots are absent.
- [ ] Public fixtures are synthetic or have confirmed redistribution rights.
- [ ] Full Git history has been scanned for secrets and private markers.

## Dependency and package safety

- [ ] Every runtime dependency required by public CI is public and resolvable without private access.
- [ ] `research-contracts` is available through a public package, release, or repository.
- [ ] The public package builds from a clean export.
- [ ] The private deployment pins an immutable public release.

## CI and verification

- [ ] Public CI runs without repository secrets.
- [ ] Public CI does not call real market-data APIs, Feishu, private networks, or production paths.
- [ ] Boundary checker passes.
- [ ] Lint, format, type check, tests, CLI checks, and package build pass in the clean export.
- [ ] Private deployment configuration and dry-run integration checks pass against the pinned public release.

## Publication

- [ ] License and dependency notices are reviewed.
- [ ] Branch protection and GitHub Actions permissions are reviewed.
- [ ] Public README and contribution guidance are complete.
- [ ] A rollback release is pinned in the private deployment repository.
- [ ] Public repository is created from a clean sanitized history, not by changing the visibility of the existing private repository.
