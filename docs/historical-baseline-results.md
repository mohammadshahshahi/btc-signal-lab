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


## v1.1 continuous-score rerun

The following run uses the same frozen BTCUSDT 1h dataset and cost assumptions,
but evaluates the v1.1 continuous-score implementation. It supersedes the
earlier v1.0 signal-rule figures above for comparisons against the current
branch; both historical records are retained for traceability.

- Workflow: [Signal Engine Unit Tests / historical-paper-backtest](https://github.com/mohammadshahshahi/btc-signal-lab/actions/runs/38259035103)
- Commit: `c027bd016589eb09fa70ef4176b11485f1f85a85`
- Artifact: [Download v1.1 reproducibility bundle](https://github.com/mohammadshahshahi/btc-signal-lab/actions/runs/38259035103/artifacts/11751816818)
- Artifact name: `btcusdt-paper-backtest-38259035103`
- Dataset: unchanged 744-candle window and SHA-256 listed above
- Costs: 0.1% fee per side and 5 bps slippage per side

| Metric | v1.1 strategy | Buy-and-hold benchmark |
|---|---:|---:|
| Final equity | 8,842.72 | 10,817.96 |
| Net return | -11.57% | +8.18% |
| Maximum drawdown | 17.68% | 11.25% |
| Closed trades | 10 | — |
| Win rate | 10.00% | — |

The strategy underperformed buy-and-hold by **19.75 percentage points** in this
one-month window. The v1.1 result is still negative and does not support a
profitability claim. This is one short historical sample, and the strategy
parameters were not selected or validated on independent regimes. The report
is a research baseline only.


The latest report bundle also includes the 24-bar forward-direction diagnostic
introduced in report schema 1.2. The artifact above is the canonical v1.1
reproducibility bundle for this PR head; the historical return figures remain
the same as the preceding v1.1 smoke run because the scoring and backtest logic
did not change in the report-integration commits.
