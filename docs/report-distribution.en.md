# Report delivery contract

[中文页面](report-distribution.md)

## Public audience model

Reports may be classified for audiences such as `client`, `internal`, and `public`. Deployment configuration supplies delivery targets; this repository stores only the classification rules and offline examples.

## Delivery guarantees

Each delivery should include an idempotency key and a delivery receipt. Repeated runs reuse confirmed receipts to prevent duplicate sends. Stop delivery when the target is missing or artifact validation fails.
