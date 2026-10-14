# Historical Backtest Contract (v0.1)

## Purpose and safety
The backtester evaluates the existing Signal Engine in offline historical research.
It is paper/research only: it has no exchange connection, order execution, API
credentials, or private-key handling. Results do not establish future profitability.

## Input data
Pass chronological candles, oldest first, with finite numeric `open`, `high`,
`low`, and `close`. Each OHLC value must fit within the candle's high/low
range. An optional `timestamp` is copied to the trade ledger; this version does
not parse or validate timestamp formats. Do not mix symbols, timeframes, or
non-contiguous samples in one run.

## Execution timing and accounting
- At candle i close, the signal function sees only candles 0 through i.
- BUY/SELL generated from candle i is eligible for execution at candle i+1 open.
- The baseline is long-only: BUY opens when flat; SELL closes an open position.
- Any remaining position is liquidated at the final candle close.
- Buy fills apply adverse slippage upward; sell fills apply adverse slippage downward.
- Fees are charged on both entry and exit notional.
- Equity is marked at each close using estimated net liquidation value.
- Reported trade PnL is net of entry/exit fees and modeled slippage.

## Metrics
The result contains initial/final equity, net profit, net return, maximum drawdown,
trade count, win rate, gross profit/loss, profit factor, average trade PnL and
return, average holding duration in bars, exposure percentage, trade ledger,
and equity curve. Profit factor is null when there is no gross loss (rather than
being represented as infinity). Exposure is the percentage of dataset candles
whose close is marked while a position is open. No annualized metrics are
reported until timestamp frequency and missing-candle handling are validated.

## Important limitations
This is a baseline simulator, not an exchange-grade fill simulator. It does not
model funding, bid/ask spread separately, partial fills, market impact, exchange
outages, or intrabar stops. Test on a frozen, documented dataset; preserve source,
retrieval date, timeframe, timezone, duplicate/gap checks, and hashes. Do not
claim performance until real historical data is downloaded, cleaned, and the
results independently reviewed. Keep the strategy and cost assumptions fixed
before evaluating a held-out period to reduce tuning bias.
