[Chinese version](ta-methodology.md)

# Technical analysis methodology

The project generates separate technical-analysis reports for BTC/USDT and XAU/USD. They share an indicator set but use different data sources and calculation engines.

## Indicators

### Simple moving average (SMA)

```text
SMA_n = (1 / n) * sum(P[t-i], i=0..n-1)
```

- BTC uses SMA50 and SMA200 with Pandas `rolling().mean()`.
- XAU uses configurable windows, defaulting to SMA50/SMA200, with a pure-Python rolling-window implementation.
- SMA50 above SMA200 is classified as a bullish golden cross; otherwise it is classified as a bearish death cross.
- Price relative to the fast average further distinguishes a bullish position from a pullback or rebound watch.

### Relative strength index (RSI)

```text
RSI = 100 - 100 / (1 + RS)
RS = average gain / average loss
```

- Default period: 14.
- BTC uses Wilder smoothing (`EWM alpha = 1/14`) implemented with Pandas.
- XAU uses standard Wilder smoothing in pure Python: a simple average initializes the first window, followed by recursive updates.
- Thresholds: overbought at or above 70; oversold at or below 30.

### Average true range (ATR)

```text
TR = max(H-L, abs(H-C_previous), abs(L-C_previous))
ATR_n = SMA(TR, n)
```

The default period is 14. BTC ATR is in USDT; XAU ATR is in US dollars. XAU `volume` is an OANDA tick count, not total-market trading volume.

### Classic floor pivots

Calculated from the previous session's OHLC:

```text
P  = (H + L + C) / 3
R1 = 2P - L       S1 = 2P - H
R2 = P + (H - L)  S2 = P - (H - L)
R3 = H + 2(P-L)   S3 = L - 2(H-P)
```

BTC uses the previous daily candle. XAU uses the previous completed daily candle (`complete=true`), with the trading day aligned to 17:00 New York time.

### Key-level proximity (XAU only)

The XAU report checks whether the current price is near S2, S1, P, R1, R2, or the previous day's high/low. The default proximity threshold is 0.1% (`near_pct=0.001`); a match appears in the report's trading notes.

## BTC module

Historical data comes from Binance daily archives; incremental data uses Binance, Kraken, and Bitstamp REST APIs.

- `init-history` downloads daily ZIP archives from `data.binance.vision` and consolidates them into Parquet.
- `fetch` refreshes incrementally, falling back in Binance → Kraken → Bitstamp order.
- Files are stored at `out/btc/klines_{1m,1h,1d}.parquet`.
- Daily data is required for reports; hourly and minute data are optional.
- `include_intraday` controls whether an intraday snapshot is included, and `intraday_granularities` selects its granularities.
- Minute reports additionally calculate 1-minute RSI14.

## XAU module

XAU data comes from the OANDA Practice REST API using midpoint prices.

Key settings in `config/ta_xau_*.yml`:

```yaml
instrument: XAU_USD
alignmentTimezone: America/New_York
dailyAlignment: 17
windows:
  sma_fast: 50
  sma_slow: 200
  rsi: 14
  atr: 14
thresholds:
  rsi_overbought: 70
  rsi_oversold: 30
  near_pct: 0.001
```

| Configuration | Granularity | Intraday snapshot | Schedule |
| --- | --- | --- | --- |
| `ta_xau_daily.yml` | D | Disabled | Weekdays at 18:00 China Standard Time (CST) |
| `ta_xau_h1.yml` | D + H1 | Enabled | Every hour at :02 |
| `ta_xau_m5.yml` | D + M5 | Enabled | Every 5 minutes at :02 |

## Limitations

- OANDA is a practice-account data source. Its volume is a tick count and is not suitable for market-wide volume analysis.
- Local DNS may resolve `api-fxpractice.oanda.com` incorrectly and cause timeouts. The OANDA workflows run on GitHub Actions; remote triggering is an available fallback when local access fails.
- TA indicators are heuristic references. Trading notes in reports state that they are not investment advice.
- When BTC daily history has fewer than 260 rows, CI backfills approximately 400 days of history.
- BTC/XAU monitoring is guarded to 06:00–16:35 US Eastern Time (ET); it does not run outside US equity trading hours.
