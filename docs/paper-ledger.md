# Paper Trading Ledger

The paper ledger is deterministic and has no broker side effects. It consumes
approved `PaperOrderIntent` values, creates simulated fills, updates cash and
positions, and returns dashboard-ready mark-to-market valuation.

## Fill Assumptions

- Buy order notional is based on starting AUM and `aum_pct`.
- Sell order quantity is based on the current paper position and `aum_pct`.
- Fills use injected quotes, never live network calls inside the ledger.
- Buy fills prefer ask price, sell fills prefer bid price, and both can apply
  configured slippage.
- Fees are applied in basis points.
- Partial fills scale notional or position quantity by `fill_ratio`.

## Live P&L

The ledger values the current `EQNR.OL` paper position from an injected latest
quote. This is the boundary that QUA-35 will connect to a live Equinor quote
provider.

Dashboard valuation includes:

- last price
- quote source and observed time
- quote freshness: `fresh`, `stale`, or `missing`
- market value
- realized P&L
- unrealized P&L
- unrealized P&L percentage
- total P&L
- total P&L percentage
