# Getting started in five minutes

[Chinese version](getting-started.zh-CN.md)

This guide installs the public framework and runs offline checks. It does not require market-provider credentials and does not send messages.

## Prerequisites

- Python 3.11, 3.12, or 3.13
- Git
- `uv`
- Node.js and npm only when developing the separate `quant-intel-pages` frontend

## Install and verify

```bash
uv sync --locked --group dev
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest
uv run python project_tools/update_cli_help.py --check
```

For the complete repository gate, run:

```bash
uv run python project_tools/check_all.py --scope all
```

The report website consumes reviewed artifacts and static snapshots from the separate Pages repository. Configure private paths explicitly when running production integrations; do not add credentials or runtime output to the repository.
