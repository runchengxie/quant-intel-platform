# A-Share External Factor-Signal Research Archive

[中文页面](a-share-factor-signals.md)

> Historical archive. Factor panels, minute features, Hermite transformations, and rolling research workflows described here have moved to owner repositories, including `quant-research` and `strategy-pipeline`. `market-intel` no longer provides the production-generation or report-observation entry points described in this note. Commands and paths below document the archived workflow; they are not current usage instructions. Results are research evidence, not investment advice.

## Scope and historical workflow

The experiments studied external factor panels joined to daily training samples by `(date, symbol)`, plus minute-level volatility and liquidity features. The panel layout used by the former workflow was `<external_factor_root>/<group>/<factor_name>.parquet`.

The archived implementation included the module entry points `a_share_analysis.factor_tools.minute_factor_smoke`, `minute_factor_expand`, `incremental_experiment`, `walk_forward`, `volume_oos_audit`, and `hermite_factor_meta`. It also used `scripts/refresh_a_share_factor_observation.sh YYYYMMDD` for an incremental download workflow. These are historical names and locations, not an assertion that this repository currently owns or installs those tools.

The former downloader coordinated with `quant-market-data-platform` and a shared TuShare minute-request quota ledger. Its documented safeguards included a single resolved credential and API URL per run, explicit request reservations, bounded retry behavior, validation before atomic parquet replacement, redacted credential provenance, and completeness receipts. A resumed batch was accepted only when its security set, trading date, and per-security minute coverage matched the expected layout. Top200 and DailyWatch20 consumers shared the ledger, while historical Top200 output retained its existing 20-symbol batch layout to avoid mixing incompatible batches.

Quota settings were expressed with machine-readable keys such as `MDP_TUSHARE_MINUTE_QUOTA_MODE`, `MDP_TUSHARE_MINUTE_QUOTA_DB`, `MDP_TUSHARE_MINUTE_QUOTA_GATE`, `MDP_TUSHARE_MINUTE_QUOTA_LIMIT_REQUESTS`, and `MDP_TUSHARE_MINUTE_QUOTA_SAFETY_REQUESTS`. The historical service policy used request-first gating; the old note's numeric limits are intentionally not repeated as current operating guidance.

## Initial smoke experiment

The 2026-07-06 local smoke covered 20 securities over five trading days, from 2026-01-05 through 2026-01-09, and calculated five factors in the `mf_volatility_32` group:

| Factor | Historical definition |
| --- | --- |
| `realized_variance` | Sum of squared one-minute log returns during the session |
| `realized_skewness` | Intraday return skewness |
| `realized_kurtosis` | Intraday return kurtosis |
| `volume_volatility` | Coefficient of variation of minute volume |
| `price_elasticity` | Intraday high-low range relative to traded value |

This was a lite smoke, not the full 32-factor panel. Next-session close-to-close Rank ICs were `-0.0734` for `price_elasticity`, `0.0078` for `realized_kurtosis`, `-0.0343` for `realized_skewness`, `-0.1402` for `realized_variance`, and `0.0406` for `volume_volatility`. Five observations are sufficient only to check wiring; they cannot establish factor efficacy.

## Top200 exploratory comparison

The historical top-200 dataset covered 137 trading days and 200 securities from 2025-10-09 through 2026-04-30. The recorded raw-minute request count was 1,370/1,370; raw and factor directories occupied about 177 MB. The expanded group contained 32 factors.

Using the first 100 days for training and the remaining 37 for testing, the recorded Top20 results were:

| Model | Mean Rank IC | Cumulative return | Maximum drawdown | Turnover | Holding overlap |
| --- | ---: | ---: | ---: | ---: | ---: |
| Daily baseline | 0.0081 | 12.08% | -9.94% | 0.374 | 0.626 |
| Baseline + lite five | 0.0065 | 8.98% | -10.41% | 0.479 | 0.521 |
| Baseline + full 32 | 0.0401 | 14.54% | -11.29% | 0.654 | 0.346 |
| Baseline + `volume_activity5` | 0.0341 | 15.81% | -9.33% | 0.499 | 0.501 |

`volume_activity5` comprised `volume_volatility`, `log_volume_volatility`, `diff_abs_mean_volume`, `peak_count_1std`, and `peak_count_2std`. It was a sparser and more interpretable candidate than `full32`, but its turnover was still higher than the baseline. These results were an exploratory fixed split, not independent confirmation.

## Rolling evaluation and costs

The historical `walk_forward` sweep evaluated training/testing windows, transaction-cost assumptions, turnover caps, holding bonuses, rebalance intervals, and score smoothing. At 20 bps, the fixed 100/37 split recorded 15.14% net return for daily `volume_activity5` with a 0.05 holding bonus and 0.50 turnover cap, versus 9.11% for the daily baseline. In a rolling 100/10 evaluation, the three-day rebalance with a 0.30 cap recorded 13.74% net return and 0.100 turnover; the baseline recorded 8.87% and 0.460 turnover. Results varied materially with the window: the 60/10 baseline net return was 0.74%, while one smoothed, capped volume variant recorded 21.33%.

Those earlier close-to-close labels included the overnight interval from `close(T)` to `open(T+1)`, even though a full minute-factor signal was not available until after the close on T. The note therefore downgraded these results to candidate screening, not tradable alpha evidence.

## Strict post-close timing audit

The later audit changed the label to `open(T+2) / open(T+1) - 1`, purged one signal date at each rolling-fold boundary, froze the `rebalance_3d_turnover_cap_0.30` policy, and reported 10/20/30/50 bps scenarios. It did not replace blocked limit-up buys or limit-down sells after observing the outcome. The simulated returns assumed target fills and were therefore an upper bound, not a complete execution simulation.

The audit also retained several evidence limits:

- `volume_activity5` had been pre-screened on overlapping historical data; the evaluation was not an untouched factor holdout and remained exposed to multiple-selection bias.
- The universe was a static Top200 list, not a point-in-time universe.
- Candidate formation used only information visible on T. Missing future labels could not be used to remove securities before scoring; missing Top20 labels, frozen holdings, or trade-status data failed closed.
- A shared two-session label-maturity period excluded the last two signal dates by calendar before scoring. Security-day lookups used the market trading calendar instead of shifting each security's rows, so suspensions did not silently roll a target date forward.
- The recorded sample had 184 candidate signal dates through 2026-07-10. The main 80/10 OOS window covered 101 days from 2026-02-03 through 2026-07-08; seven days lacked full-market active returns. At 30 bps, mean Rank IC was 0.0264 for baseline and 0.0474 for baseline plus `volume_activity5`, with paired IC increment 0.0210 and HAC t-statistic 3.69. The paired net-return increment HAC t-statistic was only 0.69.
- The 100-day training window had two missing Top20 labels and was invalidated as a full-period return inference rather than shortened to the remaining observations. For the main window, incomplete active returns also prevented a full-market active-return conclusion.
- Six limit-up buy blocks and six limit-down sell blocks were observed. The promotion status was `research_only`, and `untouched_factor_holdout=false` was an explicit failure reason.

The historical conclusion was narrow: `volume_activity5` merited more history and a larger universe, but was not established as tradable alpha and should not be promoted using the earlier close-to-close returns.

## Hermite meta-features

The former `hermite_factor_meta` transformation operated on an existing daily factor panel. It applied rolling z-scores per security and derived Hermite `h3`/`h4` energy features; it did not generate raw factors from daily or minute prices. Recorded outputs included `*_ts_h3_60`, `*_ts_h4_60`, `*_ts_closeness_60`, and `*_energy_compression_20_60`. The 60-day window required about 36 valid observations before producing a value; the archived note recommended one to two years of daily factor history for training.

As of 2026-07-06, the local Top200 panel covered 180 trading days and 200 securities, with 20 Hermite meta-panels generated. In the historical product wiring, report observations displayed research readings and Hermite generation status, while a daily hotspot-candidate preview used `volume_activity5` and Hermite closeness as low-weight ranking aids with a fallback to the original candidate order when coverage was missing. Hermite was not an independent alpha or a replacement for the original ranking.

## Reading the evidence

The original note recommended keeping the full-market daily universe and labels as a base, expanding minute data to a larger liquid universe, comparing daily baseline / minute factors / minute factors plus Hermite on the same splits, and reporting Rank IC, TopK returns, drawdown, and turnover together. That was a proposed research path, not a current product commitment.

The final historical product wording was: hotspot tracking remained primary, trading-related features were auxiliary, and the candidate watchlist was for research reference only. For current implementation, data, CLI, and strategy ownership, consult the `quant-research`, `quant-market-data-platform`, and `strategy-pipeline` repositories rather than this archived note.
