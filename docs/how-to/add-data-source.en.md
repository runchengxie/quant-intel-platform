# Add a data source

[中文页面](add-data-source.md)

Before adding a source, identify the report or contract it serves. Small changes may extend an existing fetcher; larger changes should begin with a data-contract document.

## Recommended steps

1. Define the data's use and refresh frequency.
2. Specify fields, dates, provenance, and missing-data states.
3. Implement the fetcher under `src/daily_messenger/etl/fetchers/` or the corresponding module.
4. Test successful responses, empty results, timeouts, and fallback behavior.
5. Connect the result to the report or snapshot workflow.
6. Update related documentation and CLI help.

## Minimum contract

Document the source, the date represented by each record, required fields, failure representation, whether a previous period may be used, and whether CI may call the live endpoint.

## Code ownership

Global-market data usually belongs under `src/daily_messenger/etl/fetchers/`; A-share report data usually belongs under `src/a_share_daily/`. Cross-repository research artifacts should be consumed through their owner-specific validation module. Do not copy research-repository implementations into this project.

## Local verification

```bash
uv run pytest
uv run ruff check .
uv run ty check
uv run mkdocs build --strict
```

Tests should use synthetic fixtures. Real credentials and production snapshots belong only in the deployment environment.
