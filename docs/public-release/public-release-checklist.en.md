# Public Release Checklist

[Chinese version](public-release-checklist.md)

Complete these checks before creating or updating a public GitHub repository. Keep production history in the private repository until all checks are complete.

## Release record

Before release, record these values in the private deploy repository:

- `source_revision`: the last reviewed commit in the private source
- `public_revision`: the root commit of the clean export
- `public_release_tag`: the immutable public release tag
- `deploy_platform_pin`: the 40-character commit used by deploy
- `rollback_platform_pin`: the verified 40-character rollback commit

## Repository boundary

- [ ] `file-migration-manifest.yml` covers every tracked file
- [ ] Public source uses semantic audience names only
- [ ] Production schedules, recovery bridges, and host configuration are in the private repository
- [ ] Public source does not import, check out, or depend on private deployment code
- [ ] Public source does not use implicit production file paths

## Data and privacy

- [ ] The public tree contains no real customer, partner, group, user, or internal-document identifiers
- [ ] The public tree contains no real webhook, chat ID, token, credential, private endpoint, or proxy label
- [ ] `state/`, `out/`, receipts, logs, and provider snapshots are not published
- [ ] Public fixtures are synthetic or confirmed to be redistributable
- [ ] Git history has been scanned for secrets and private markers

## Dependencies and build

- [ ] Public CI runtime dependencies resolve without private access
- [ ] `research-contracts` is available through a public package, release, or repository
- [ ] The public package builds from a clean export
- [ ] Private deploy pins an immutable public release

## CI and validation

- [ ] Public CI does not depend on repository secrets
- [ ] Public CI does not access live market APIs, Feishu, private networks, or production paths
- [ ] The boundary checker passes
- [ ] Lint, formatting, type checks, tests, CLI checks, and package build pass
- [ ] Private deploy completes a dry-run against the public release

## After release

- [ ] License and dependency declarations have been reviewed
- [ ] Branch protection and GitHub Actions permissions have been reviewed
- [ ] README and contribution guide are complete
- [ ] Private deploy records a rollback release
- [ ] The public repository was created from a clean history, without changing the private repository's visibility
