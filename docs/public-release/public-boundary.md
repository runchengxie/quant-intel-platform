# Public Boundary

`quant-intel-platform` is the reusable public framework for consuming
versioned research/data artifacts, validating them, rendering reports and
dashboards, and exposing generic delivery interfaces.

The public repository does not own production deployment policy. Real
credentials, destination mappings, host scheduler installation, private owner
repository roots, production state, logs, receipts, and customer artifacts
belong to `quant-intel-deploy` or to the deployment environment.

Public code communicates across repository boundaries through installed public
CLI commands, versioned file contracts, and explicitly supplied environment
variables. It must run its quality gates with no private checkout, secret,
private network, production path, or real customer data.

The public CI workflows are quality gates only. They do not fetch production
data, send messages, write snapshots, enable schedulers, or mutate deployment
state.
