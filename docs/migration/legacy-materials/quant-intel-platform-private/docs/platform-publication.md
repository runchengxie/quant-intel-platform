# Research platform publication consumer

`market-intel` can consume `research.platform-publication.v1` bundles produced by `research-workspace` without importing research owner implementation code.

## Role

The publication manifest is a handoff index, not a new data lake. `market-intel` uses it to locate already-approved projections that may be rendered into reports, delivery cards, or operator views.

The consumer verifies:

- manifest schema through the pinned `research-contracts` package;
- explicit `market-intel` consumer declaration;
- disclosure audience (`public` or `internal`);
- safe bundle-relative paths;
- file existence;
- SHA-256 content identity.

`verify_platform_publication()` returns resolved, verified paths. It does not load model objects, call research internals, or infer missing artifacts.

## Disclosure modes

Operational/report generation may use `allow_internal=True` when the deployment is explicitly internal. Public-only rendering must use `allow_internal=False`; an internal artifact explicitly targeted at `market-intel` then fails closed.

## Relationship to existing artifacts

DailyWatch20, style-factor, D11-H5 and other established contracts remain valid. The publication manifest provides a common envelope for future cross-surface projection and does not replace strategy-specific validation.

## Rollout

This PR is stacked on the `research-workspace` platform-publication contract branch. Before merge:

1. merge the upstream workspace contract;
2. refresh the `research-contracts` pin to the resulting workspace `main` commit;
3. run `uv lock` and commit the updated `uv.lock`;
4. run the normal market-intel quality gates.

## Production-shaped fixture

`tests/fixtures/publications/daily_watch20/` contains a synthetic internal
DailyWatch20 bundle with a watchlist, selection receipt, and publication
manifest. It exercises the same consumer path as a deployed handoff while
keeping real symbols, provider data, credentials, and private paths out of
the repository. The fixture must pass with `allow_internal=True` and fail
closed for public-only consumption.
