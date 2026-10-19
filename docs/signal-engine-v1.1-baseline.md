# Signal Engine v1.1 — Frozen Exploratory Baseline

**Status:** frozen exploratory baseline; not a profitability claim and not an approved final-test candidate.  
**Evaluated commit:** `2fa9ee8048366fdc7f21309188d7a0862769be1c` (networked Multi-Regime run #21).  
**Signal contract:** `docs/signal-engine-contract.md`, schema version 1.1.  
**Primary evaluation assumptions:** BTCUSDT Spot; initial equity 10,000 quote-currency units; fee 0.1% per side; slippage 5 bps per side; signal calculated at candle close and earliest execution at next candle open.

## Signal definition

Indicators:
- EMA20 and EMA50, SMA-seeded; subsequent EMA recursion uses alpha = 2 / (period + 1).
- RSI14 using Wilder smoothing.
- MACD(12, 26, 9), component EMAs SMA-seeded.
- ATR14 using Wilder smoothing; first true range is high minus low.
- Volume SMA20 and volume ratio are context-only; volume does not independently set direction.

Score components (each bounded to [-1, 1]):
- trend = tanh(4 × (EMA20 − EMA50) / ATR14)
- price_vs_ema20 = tanh(2 × (close − EMA20) / ATR14)
- macd_momentum = tanh(20 × (MACD − MACD_signal) / ATR14)
- rsi_momentum = clamp((RSI14 − 50) / 20, -1, 1)

Composite = 0.35 × trend + 0.20 × price_vs_ema20 + 0.25 × macd_momentum + 0.20 × rsi_momentum.  
Score = clamp(50 + 50 × composite, 0, 100).

Decision thresholds:
- Score >= 70: BUY / LONG.
- Score <= 30: SELL / SHORT label.
- Otherwise: HOLD / NEUTRAL.
- Insufficient indicator history: score 50, HOLD / NEUTRAL.

The score is a deterministic heuristic strength index, not a probability or calibrated confidence.

## Execution and accounting assumptions

- Paper-only, long-only simulator: BUY opens a long position; SELL closes it and does not open a short.
- No exchange credentials, real orders, leverage, funding, partial fills, or market-impact model.
- Costs in the primary registered runs: 0.1% fee per side and 5 bps slippage per side.
- Backtest convention: signal at candle close, fill no earlier than next candle open.
- Forward-horizon diagnostic uses a 24-bar horizon and overlapping observations; it is not fill-level PnL and must not be conflated with the portfolio backtest.

## Exposed exploratory evidence

Run #21: https://github.com/mohammadshahshahi/btc-signal-lab/actions/runs/38596348454

Five of six matrix artifacts passed independent row-count, exact CSV SHA-256, UTC boundary, and interval-continuity checks:
- Bear 1h: strategy -65.49%; Buy & Hold -66.81%.
- Bear 4h: strategy -46.61%; Buy & Hold -65.90%.
- Recovery 4h: strategy +92.37%; Buy & Hold +154.99%.
- Bull 1h: strategy +43.51%; Buy & Hold +119.65%.
- Bull 4h: strategy +51.62%; Buy & Hold +120.40%.
- Recovery 1h: unavailable; Binance Spot 1m archive has a genuine 80-minute gap (2023-03-24 12:40–13:59 UTC). Strict aggregation correctly failed closed; no synthetic candle was created.

Across all five available windows, net return trails cost-aware Buy & Hold. These windows have been exposed and are exploratory/validation evidence only. They must not be re-described as untouched test data or used to claim unbiased final-test performance.

## Known limitations

- Long-only execution; SELL is an exit, not a short entry.
- No funding, market impact, partial fills, order-book spread model, latency, or exchange execution.
- Fixed cost assumptions may understate costs; higher-cost sensitivity remains required for future candidates.
- Coarse regime labels do not imply every candle belongs to the same regime.
- The 24-bar forward diagnostic overlaps and is not an independent trade-level return series.
- Recovery/1h has no valid dataset from currently tested sources.
- Existing report metadata inconsistently classified exposed windows as validation; this is a governance/protocol issue, not permission to relabel historical results retrospectively.

## Freeze policy

1. Do not modify v1.1 weights, thresholds, indicator definitions, or execution assumptions to improve these already inspected results.
2. Preserve this document, evaluated commit, datasets/manifests, reports, and CI evidence as the baseline record.
3. Any strategy redesign or parameter search must be a separately versioned candidate (v2) with a pre-registered hypothesis, search space, objective, costs, benchmarks, risk limits, and time-ordered validation.
4. Do not fetch or inspect candidate final-test data (currently proposed 2025-02-01 through 2026-02-01) until both contributors explicitly attest YES/NO/UNSURE on prior exposure and approve exact boundaries and protocol. If either has seen/used it or cannot attest, choose a later holdout or classify it as exposed.
5. No live trading or exchange credentials are in scope.

## Related records

- Research plan: https://github.com/mohammadshahshahi/btc-signal-lab/issues/13
- Protocol/exposure gate: https://github.com/mohammadshahshahi/btc-signal-lab/issues/2
- Data validation: https://github.com/mohammadshahshahi/btc-signal-lab/pull/8
- Evaluation harness: https://github.com/mohammadshahshahi/btc-signal-lab/pull/11
- Strict 1m aggregation: https://github.com/mohammadshahshahi/btc-signal-lab/pull/12
