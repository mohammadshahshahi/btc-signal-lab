# btc-signal-lab
Automated BTC/USDT market analysis and 24-hour signal generation with scheduled execution, technical indicators, historical signal aggregation, backtesting, and paper trading. Built as a collaborative research MVP — no live trading or exchange API keys.

## Current-market paper signals vs. historical validation

The current signal path and historical backtests are intentionally separate:

- `src/btc_signal_lab/live_market_data.py` fetches recent public Binance Spot candles, discards the still-forming candle, and fails closed on gaps, malformed rows, insufficient history, or stale data. It records source, observation time, newest closed candle, response SHA-256, and confirms that no live order was submitted.
- `.github/workflows/current-paper-signal.yml` generates a paper-only BTCUSDT signal hourly and can also be run manually for 15m, 1h, or 4h. Each run uploads a JSON artifact with the signal, code commit, and data provenance. Scheduled workflows run only from the repository's default branch; merge this workflow before expecting scheduled runs.
- Historical workflows remain responsible for reproducible backtests and regime validation. A failure in a 2023 historical window must not be silently patched or treated as proof that current candles are invalid; it remains a separate historical-data blocker.
- The live workflow does not place orders, guarantee uptime, or establish profitability. A successful run proves only that one fresh input window was fetched and a deterministic paper signal was produced.

### Known historical blocker

The 2023 recovery / 1h validation window currently fails closed because Binance's monthly and daily 1m archives both omit 80 consecutive minutes on 2023-03-24. The code preserves archive URLs and SHA-256 evidence and does not synthesize candles or silently combine exchanges. Keep the multi-regime validation PR in Draft until that source defect is resolved with defensible evidence or the affected historical window is formally excluded from the protocol.

