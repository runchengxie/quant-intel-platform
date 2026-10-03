# Set up a new machine

[Chinese version](new-machine-setup.md)

## Local development

Install Python, `uv`, and Git, then run from the repository root:

```bash
uv sync --locked --group dev
uv run pytest
uv run mkdocs serve
```

## Production boundary

Production credentials, schedules, research-repository paths, and delivery configuration are managed by `quant-intel-deploy`. This repository contains public code, example configuration, offline fixtures, and documentation only.
