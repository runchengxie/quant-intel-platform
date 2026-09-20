# Private Deployment Migration Notes

The private deployment repository is scaffolded at `/home/richard/code/quant/quant-intel-deploy` for local validation and will be published separately as a private repository.

## Assets that belong in private deployment

The following tracked asset families are production-only and must be moved before the public export is created:

- `scripts/systemd/` and `scripts/windows/` scheduler definitions;
- `scripts/setup_cron.sh` and host installation helpers;
- report refresh, DailyWatch20 delivery, weekly recap, supervisor, and recovery bridges;
- production audience aliases and destination mappings;
- production data, state, output, receipt, and log roots;
- internal runbooks and escalation details.

The public framework retains only generic CLI behavior, artifact validation, rendering, offline fixtures, and public-safe contracts. Private bridges must invoke those public interfaces using explicit environment variables and pinned releases.

## Current staging state

The private repository currently contains configuration and directory skeletons plus a staging framework revision. Actual scheduler and production bridge migration remains a cutover task because the public release history must first be created from a clean sanitized export.

The private `production` dependency extra is intentionally disabled until the public repository publishes its first release tag.
