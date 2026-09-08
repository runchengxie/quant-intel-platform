# Delivery Agent Workflow

This document describes the public delivery abstraction. A deployment may use a command-line delivery agent, a webhook adapter, or another transport that implements the same contract.

## Contract

The delivery layer receives:

- rendered text or image artifacts;
- a semantic audience;
- an idempotency scope;
- an optional dry-run flag.

It returns a delivery result and records the artifact hash, target fingerprint, and outcome in the receipt. Target fingerprints must be redacted and must not reveal credentials.

## Production configuration

The public repository does not choose real destinations. `market-intel-deploy` supplies transport binaries, environment variables, audience mappings, and operational schedules.
