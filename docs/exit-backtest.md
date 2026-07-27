# Exit Anchor Backtest

The exit backtest compares the user's core timing idea: sell 30, 40, or 50
minutes after the first Norwegian market-facing confirmation, then compare those
results with exits anchored to earlier operational timestamps.

## Recorded Timestamps

Each replay case records:

- first official signal time
- first source ingestion time
- first Norwegian confirmation time, when available
- paper order entry time

## Exit Variants

For each case, the simulator evaluates 30, 40, and 50 minute exits from:

- `norwegian_confirmation`
- `first_seen_signal`
- `order_entry`

If no Norwegian confirmation exists, Norwegian-anchor variants are omitted and
the case is marked `missing`. If confirmation arrives after the configured
fallback window, the case is marked `late`.

## Metrics

Each exit variant reports:

- target and actual exit times
- entry and exit execution prices
- slippage and spread assumptions
- gross and net paper P&L percentage
- paper P&L as percentage of AUM allocation
- peak favorable excursion
- max drawdown
