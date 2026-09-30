# Public Repository Boundary

[中文页面](public-boundary.md)

`quant-intel-platform` is a reusable public framework. It consumes versioned research and data artifacts, validates them, generates reports and dashboards, and provides general-purpose delivery interfaces.

The following belong in `quant-intel-deploy` or the specific deployment environment and must not be placed in the public repository:

- Real credentials and delivery targets
- Host schedules and installation configuration
- Private research repository paths
- Production state, logs, and receipts
- Customer data and real runtime outputs

Cross-repository integrations use installed public CLIs, versioned file contracts, and explicitly provided environment variables. Public-repository quality checks do not depend on private checkouts, secrets, private networks, production paths, or real customer data.

Public CI performs quality checks only. It does not fetch production data, send messages, write snapshots, enable timers, or change deployment state.
