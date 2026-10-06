# Stable report test fixtures

Goal: Keep website regression checks valid as the five-date public snapshot rotates.

Scope: web/tests only. Preserve runtime validation, public snapshots, assertions, and production release pins.

- [x] Reproduce all three website failures against PR #206's public snapshot.
- [x] Preserve the previously public rendering sample as a named regression fixture with source provenance.
- [x] Build history and watchpoint tests from explicit fixtures instead of transient public report identities or outcomes.
- [x] Run the targeted tests against both current main and PR #206 snapshots, then all applicable website checks and full platform gate.
- [ ] Open a fix PR, wait for required CI, merge, and then update/revalidate the report PR before merging it.
- [ ] Preserve unknown history and runtime artifacts during cleanup; keep production current untouched.

Validation: three targeted checks fail before and pass after against PR #206; 132 Node, 317 website Python, 1,199 platform Python and 12 browser checks pass. Website coverage is 85.04%. Python tests use TMPDIR=/var/tmp to avoid the local /tmp/.git marker. Optional shellcheck and shfmt are unavailable; bash syntax and other gates passed.
