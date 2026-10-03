# Report structure

[Chinese version](report-structure.md)

## Public contract

A report contains market facts, research artifacts, an interpretation layer, and provenance. Versioned fields connect these components. See [Artifact contracts](contracts.md) for the exact fields.

## Offline behavior

Without credentials or a delivery target, the platform can still render reports offline and run contract tests. Missing optional data is represented as a status and must not be presented as observed data.
