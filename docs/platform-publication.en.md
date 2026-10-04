[Chinese version](platform-publication.md)

# Consuming research platform publications

The repository name is `quant-intel-platform`. The manifest consumer ID remains `market-intel` for compatibility with existing producers and consumers; do not substitute the repository name in this field.

`quant-intel-platform` can read `research.platform-publication.v1` packages produced by `quant-research`, `quant-platform`, or `strategy-pipeline` without importing their implementation code.

## Purpose

The publication manifest is a handoff index. `quant-intel-platform` uses it to locate reviewed projections and render them in reports, delivery cards, or operational pages.

The consumer verifies that:

- The manifest structure passes validation by the pinned `research-contracts` package.
- `market-intel` is explicitly declared as a consumer.
- The disclosure scope is `public` or `internal`.
- Relative paths inside the package are safe.
- Referenced files exist and their SHA-256 hashes match.

`verify_platform_publication()` returns resolved, validated paths. It does not load model objects, call owner-private code, or guess at missing outputs.

## Disclosure modes

Jobs or reports in an explicitly internal deployment may use `allow_internal=True`. Rendering intended only for public content must use `allow_internal=False`. Validation fails safely when an internal artifact is explicitly restricted to `market-intel` only.

## Relationship to existing artifacts

Existing contracts for DailyWatch20, style factors, D11-H5, and other outputs remain in force. The publication manifest provides a common envelope for future cross-system use of research results; it does not replace strategy-specific validation.

## Release procedure

This change depends on the owner-side platform-publication contract. Before merging:

1. Merge the contract changes from the upstream workspace.
2. Pin `research-contracts` to the latest commit on the workspace `main` branch.
3. Run `uv lock` and commit the updated `uv.lock`.
4. Run the normal `quant-intel-platform` quality checks.

## Production-like fixture

`tests/fixtures/publications/daily_watch20/` contains a simulated internal DailyWatch20 package with a watchlist, selection receipt, and publication manifest. It exercises the same consumer path used for deployment handoffs without checking real security codes, vendor data, credentials, or private paths into the repository. The fixture must pass with `allow_internal=True` and fail safely in public-only consumption mode.
