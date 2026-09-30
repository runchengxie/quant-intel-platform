# Artifact contracts

[中文页面](contracts.zh-CN.md)

The JSON structures in this repository define the minimum fields for important artifacts. A change that breaks these contracts is a breaking change.

Consumers should validate schema, artifact date, source freshness, and content hash before rendering or delivery. A missing, stale, or unverifiable artifact must produce a visible failure or degraded receipt; it must not be presented as a fresh successful report.

Cross-repository consumers use versioned files and public CLI contracts. They must not import business code from the owner repository. Keep evidence identifiers, source URLs, source times, publication status, and receipt fields stable and machine-readable.
