[中文页面](scoring.md)

# Theme scoring methodology

## Overview

The scoring system reads five dimensions from ETL output `raw_market.json` and combines them into a weighted theme score from 0 to 100.

## Dimensions

| Dimension | Default weight | Source | Calculation |
| --- | ---: | --- | --- |
| `fundamental` | 0.30 | Theme market performance | `_scale(perf, midpoint=1.0, sensitivity=40)` |
| `valuation` | 0.25 | Average P/E | `_inverse_ratio_score(pe, baseline=35, sensitivity=90)` |
| `sentiment` | 0.20 | Cboe Put/Call and AAII | Z-score, `tanh` compression, then mapping to 0–100 |
| `liquidity` | 0.15 | Average P/S | `_inverse_ratio_score(ps, baseline=8, sensitivity=70)` |
| `event` | 0.10 | Macro events and earnings | Fixed value or event-intensity mapping |

## Scoring functions

### `_scale(value, midpoint, sensitivity)`

Linear mapping to 0–100:

```text
score = 50 + (value - midpoint) * sensitivity
```

The result is clamped to `[0, 100]`.

### `_inverse_ratio_score(value, baseline, sensitivity)`

For valuation metrics such as P/E and P/S, lower values score better:

```text
_scale(baseline / value, midpoint=1.0, sensitivity)
```

### Sentiment aggregation (`sentiment.aggregate`)

1. Put/Call ratio: calculate a z-score from the log ratio, invert it (panic is contrarian bullish), then apply `tanh` compression.
2. AAII bull-bear spread: calculate a z-score and invert it (extreme optimism is contrarian bearish), then apply `tanh` compression.
3. Combine components as `50 + 50 * mean(component_scores)` and clamp to `[0, 100]`.

History retains up to 252 Put/Call observations and 104 AAII observations.

## Weight configuration

`config/weights.yml` supports per-theme overrides of the defaults:

```yaml
weights:
  default:
    fundamental: 0.30
    valuation: 0.25
    sentiment: 0.20
    liquidity: 0.15
    event: 0.10
  theme_ai:
    fundamental: 0.30
    valuation: 0.15
    sentiment: 0.25
    liquidity: 0.20
    event: 0.10
  theme_btc:
    fundamental: 0.10
    valuation: 0.15
    sentiment: 0.30
    liquidity: 0.30
    event: 0.15
```

## Thresholds and actions

| Key | Default | Meaning |
| --- | ---: | --- |
| `action_add` | 75 | A total score at or above this value raises the attention level |
| `action_trim` | 45 | A total score at or below this value lowers the attention level |

## Fallback behavior

When ETL fails or data is missing:

- Missing dimensions use the neutral value `50` or a historical cache.
- `scores.json.degraded` is set to `true`.
- The daily report marks delayed data in its title and cards.
- A dimension with `fallback: true` indicates that a fallback value was used.

## Updating the configuration

When changing `config/weights.yml`:

1. Update `version` and `changed_at`.
2. Run `pytest -k contract` to check contract tests.
3. Update expected values in `tests/test_scoring.py`.
