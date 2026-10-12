# Pre-registered Multi-Regime Validation Protocol (v1.0)

## Research gate

This protocol is fixed before collecting results. It evaluates the existing Signal Engine without changing indicator definitions, component weights, score normalization, or BUY/SELL thresholds. The held-out windows must not be used to tune those parameters. If parameters are changed later, that is a new strategy version and requires new untouched test data.

## Frozen windows

Each interval is evaluated separately on the same three non-overlapping, chronological windows:

| Window label | Start UTC (inclusive) | End UTC (exclusive) | Intended regime coverage |
|---|---|---|---|
| Bear-market | 2021-11-01 00:00 | 2022-11-01 00:00 | Broad BTC drawdown / bear phase |
| Recovery | 2023-01-01 00:00 | 2024-01-01 00:00 | Recovery and sustained upward trend |
| Bull-market | 2024-01-01 00:00 | 2025-01-01 00:00 | Bullish market phase |

Timeframes: 1h and 4h. Boundaries are UTC and aligned to candle opens. These are coarse regime labels, not a claim that every candle in a window shares the same regime. The windows are separated chronologically; no random shuffling is allowed.

## Fixed assumptions

- Symbol/source: BTCUSDT spot candles from the public Binance market-data mirror.
- Starting equity: 10,000 quote-currency units.
- Fee: 0.1% per side (0.001 fraction).
- Slippage: 5 bps per side.
- Signal uses data through candle close; execution is no earlier than the next candle open.
- Long-only execution: BUY enters, SELL exits; SELL does not open a short.
- Compare with cost-aware buy-and-hold and a cash-only flat baseline (0% return, 0% drawdown, zero trades).
- No leverage, funding, partial fills, market impact, or claim of profitability.

The workflow exposes fee/slippage inputs for sensitivity analysis. For the primary pre-registered run, keep the defaults above; any sensitivity run must be labeled separately and must not replace the primary run.

## Reproducibility and acceptance

The workflow runs each of the six window/timeframe combinations independently and stores the normalized CSV, SHA-256 manifest, complete JSON report, and summary as a 90-day artifact. Each summary records the evaluated commit. Dataset integrity, timestamp continuity, candle count, and report metric presence are checked before an artifact is uploaded. Data are not committed to Git.

Do not aggregate the six outputs into a profitability claim until all six artifacts are available and reviewed. Report every window, including losses and failed downloads. A window is not silently dropped if its data source fails; the workflow must be rerun or the failure documented.

## Merge gate checklist

The PR must remain Draft until all of the following are true:

- [ ] The primary run completed all six matrix combinations using the frozen default fee and slippage assumptions.
- [ ] All six reproducibility artifacts are present and linked from the PR.
- [ ] Every window's dataset row count, UTC boundaries, candle continuity, source URL, and SHA-256 are verified.
- [ ] Strategy return, maximum drawdown, trade count, win rate, profit factor, exposure, and average trade metrics are reviewed for every window.
- [ ] Results are compared against both cost-aware buy-and-hold and the cash-only baseline.
- [ ] Failed or missing matrix jobs are documented and rerun; no window is silently omitted.
- [ ] No strategy parameters were tuned against these held-out windows.
- [ ] The final PR description records the validation run URL, evaluated commit SHA, artifact links, and limitations.

A green unit-test workflow or a successful single-window smoke test does not satisfy this gate. If any result is negative or inconclusive, report it as such; do not change thresholds to make these same held-out windows pass. Parameter changes require a new strategy version and untouched evaluation data.

## Limitations

This is a research validation gate, not investment advice or a promise of future performance. The 24-bar forward-horizon diagnostic has overlapping observations and is not fill-level PnL. Results remain sensitive to fees, slippage, spot-market microstructure, and the long-only assumption. A buy-and-hold comparator is descriptive and not risk-adjusted by itself. Parameters must not be selected using these held-out windows.
