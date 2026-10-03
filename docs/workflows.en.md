# Workflows

[Chinese version](workflows.md)

## Public workflows

Public CI runs repository-boundary checks, Ruff, type checks, offline contract tests, documentation builds, and Python package builds. It does not read production credentials, fetch live data, or send messages.

## Private workflows

Production scheduling, live-data refresh, message delivery, receipt storage, and deployment validation are managed by `quant-intel-deploy`.
