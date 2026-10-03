# Delivery-agent workflow

[Chinese version](hermes-agent-workflow.md)

## Contract

The delivery agent calls public entry points, passes parameters, and stores receipts. The platform generates report content; `quant-intel-deploy` owns production schedules and live-delivery configuration.

## Production configuration

Production bots, destination chats, schedules, and log paths do not belong in this public repository. Deployment provides them through environment variables and templates in the deploy repository.
