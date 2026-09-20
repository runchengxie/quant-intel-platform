# New Machine Setup

This public repository documents local development only. Production machines must be bootstrapped from the private deployment repository and its reviewed environment configuration.

## Local development

```bash
uv sync --locked --group dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run ty check
```

External data access is opt-in. Set `DATA_PLATFORM_ROOT` to a local data root when running commands that consume published data artifacts. The framework never invents a machine-specific data path.

## Production boundary

The private deployment project supplies:

- stable checkout paths;
- owner CLI locations;
- schedules and service definitions;
- credentials and destination mappings;
- production data roots;
- recovery and escalation procedures.

Do not copy production environment files, state, receipts, or credentials into this repository.
