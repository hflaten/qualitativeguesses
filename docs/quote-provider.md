# Live Quote Provider

QUA-35 adds the market-data boundary used to mark the current paper position to
market. It does not introduce broker connectivity or live trading.

## Runtime Settings

- `QUOTE_SOURCE`: `yahoo` by default, or `disabled` to return missing quotes.
- `QUOTE_INSTRUMENT`: internal instrument name, default `EQNR.OL`.
- `QUOTE_YAHOO_SYMBOL`: upstream Yahoo chart symbol, default `EQNR.OL`.
- `QUOTE_STALE_AFTER_SECONDS`: dashboard freshness threshold, default `60`.
- `QUOTE_TIMEOUT_SECONDS`: HTTP request timeout for the quote provider.

## Dashboard Contract

The provider returns an injected `MarketQuote` for the paper ledger:

- last price
- bid and ask when available
- timestamp
- currency
- source

The ledger then marks quotes as `fresh`, `stale`, or `missing` at valuation
time. The dashboard must show stale or missing states clearly and avoid
presenting misleading live P&L.

## Provider Notes

The v1 implementation uses Yahoo chart data for `EQNR.OL` because it requires
no trading credentials and keeps paper trading deployable early. Production
market-data quality can later be upgraded behind the same `QuoteProvider`
protocol, for example to an exchange, broker, or paid market-data feed.
