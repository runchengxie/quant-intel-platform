# Platform Publication Consumer Design

## Goal

Allow `market-intel` to consume workspace publication bundles through the existing cross-repository artifact boundary while preserving report/distribution ownership and fail-closed validation.

## Design

A small `ops_common.platform_publication` consumer reads `platform-publication.json`, delegates canonical manifest validation to the pinned `research-contracts` package, selects only artifacts explicitly targeted at `market-intel`, resolves files relative to the bundle root, verifies SHA-256, and returns immutable receipt objects.

Internal publication remains an explicit operational mode. Public-only renderers set `allow_internal=False`. No research algorithm or sibling-repository source import is introduced.

## Rollout constraint

This change is stacked on the upstream workspace contract. The feature branch may temporarily pin `research-contracts` to the upstream feature commit for review. Merge requires repinning to the merged workspace `main` commit and regenerating `uv.lock` with the repository's normal tooling.
