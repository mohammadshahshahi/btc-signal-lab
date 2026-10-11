# Historical BTCUSDT Baseline Evaluation

## Purpose and scope

This is the first real-data smoke evaluation of the deterministic Signal Engine and long-only paper backtester. It validates that public OHLCV data can be retrieved, normalized, provenance-hashed, and evaluated end-to-end. It is **not** a statistically sufficient strategy validation and must not be interpreted as a profitability claim.

## Frozen run

- Workflow: [Signal Engine Unit Tests / historical-paper-backtest](https://github.com/mohammadshahshahi/btc-signal-lab/actions/runs/38184740121)
- Commit: `22d50753eb48f864ea73294f81410d1bab00400c`
- Artifact: [Download reproducibility bundle](https://github.com/mohammadshahshahi/btc-signal-lab/actions/runs/38184740121)
- Artifact name: `btcusdt-paper-backtest-38184740121`
- Artifact ID: `11718887938`
- Source: Binance public market-data mirror, `https://data-api.binance.vision/api/v3/klines`
- Symbol / interval: `BTCUSDT` / `1h`
- Window: `[2025-01-01T00:00:00Z, 2025-02-01T00:00:00Z)`
- Candles: 744
- CSV SHA-256: `359d4998d35dec28d47b924c1b2b8f13de45d93f97e6595d381e39a9b2f57d0f`
- Starting equity: 10,000 quote-currency units
- Fee assumption: 0.1% per side
- Slippage assumption: 5 basis points per side
- Execution: signal at candle close, fill at next candle open; long-only; any open position is liquidated at the final close.

## Observed result

| Metric | Result |
|---|---:|
| Final equity | 8,799.85 |
| Net profit / loss | -1,200.15 |
| Net return | -12.00% |
| Maximum drawdown | 19.05% |
| Closed trades | 9 |
| Winning-trade rate | 11.11% |

**Interpretation: this baseline failed this particular one-month evaluation window after modeled fees and slippage.** Do not present it as profitable or suitable for live trading. A single month is not enough to infer general performance; the result is a reason to investigate trade-level behavior, accounting assumptions, and out-of-sample robustness—not to tune thresholds against this window and claim success.

## Reproducibility and limitations

The workflow artifact contains the normalized CSV, adjacent JSON manifest, complete JSON report, and summary. The dataset is not committed to Git. The manifest records retrieval time, source, row count, requested range, and CSV hash.

This first run used the Binance public market-data mirror after the standard API endpoint returned HTTP 451 from the GitHub-hosted runner. No API key or exchange credential was used. No live order was placed.

Before any stronger scientific conclusion, evaluate multiple distinct regimes with a predeclared train/validation/test split, compare against buy-and-hold and simple baselines, report trade-level costs and risk metrics, and avoid selecting parameters on the final test window.
