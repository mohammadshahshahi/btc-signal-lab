# Multi-Regime Validation Protocol (v1.1 — partition clarification)

## Purpose and status

This protocol evaluates the existing Signal Engine without changing indicator
definitions, component weights, score normalization, or BUY/SELL thresholds.
It is a research gate, not evidence of profitability.

**Important status correction:** the three windows below have already been
exposed to a validation run and at least one failure/result has been inspected.
They must therefore be treated as **development/validation evidence**, not as
an untouched final test set. No future strategy selection or tuning may use
these windows while also claiming an unbiased final-test result.

## Data partitions

**Governance blocker — roles are not jointly approved.** This draft's table below
reflects the current PR proposal only. Issue #2 separately proposed the
2021-11-01–2022-11-01 bear window as development/train and 2023 as validation.
Those role assignments conflict; neither proposal is authoritative until both
collaborators explicitly reconcile and approve the exact boundaries and roles.
The already-inspected 2021–2025 results remain exposed evidence regardless of
the eventual labels. Do not retroactively relabel prior results, use them to
claim unbiased generalization, or start a final-test workflow while this
decision is unresolved. The proposed 2025-02-01–2026-02-01 interval is now
classified as exposure-unknown for governance purposes and must not be called
an untouched holdout.

Use strictly chronological, non-overlapping partitions:

| Partition | UTC range | Permitted use | Status |
|---|---|---|---|
| Development | From available history through 2021-10-31 23:59:59 | Feature/logic development and exploratory diagnostics | Development only; document every iteration |
| Validation | 2021-11-01 through 2025-01-01 (end exclusive, using the windows below) | Compare fixed candidates and diagnose robustness; any candidate selection must be recorded | Already exposed; not an untouched final test |
| Reserved final test (proposal) | 2025-02-01 through 2026-02-01 (end exclusive) | One-time evaluation of one frozen candidate, after approval | **Do not download/evaluate until both collaborators agree to freeze the candidate and confirm this partition has not been used** |

The January 2025 smoke-test period (2025-01-01 through 2025-02-01) is excluded
from the proposed final test because it has already been inspected. The proposed
final-test range is a reservation, not authorization to run it. If either
collaborator has already used that range to choose or tune parameters, agree on
a later untouched period before evaluation. Record the agreement and candidate
commit in the PR before fetching the final-test data.

The partition proposal must be accepted by both collaborators before the
reserved final-test run. If the project's Issue #2 requires a different split,
resolve that difference by mutual agreement before inspecting any final-test
results.

## Existing validation windows

| Window label | Start UTC (inclusive) | End UTC (exclusive) | Intended regime coverage |
|---|---|---|---|
| Bear-market | 2021-11-01 00:00 | 2022-11-01 00:00 | Broad BTC drawdown / bear phase |
| Recovery | 2023-01-01 00:00 | 2024-01-01 00:00 | Recovery and sustained upward trend |
| Bull-market | 2024-01-01 00:00 | 2025-01-01 00:00 | Bullish market phase |

Evaluate each window separately at 1h and 4h. These are coarse regime labels,
not a claim that every candle in a window shares the same regime. The windows
are now validation evidence only; they are not untouched held-out tests.

## Fixed assumptions

- Symbol: BTCUSDT spot candles from public sources, with the actual accepted
  source recorded in each manifest.
- Starting equity: 10,000 quote-currency units.
- Primary fee: 0.1% per side (0.001 fraction).
- Primary slippage: 5 bps per side.
- Signal uses data through candle close; execution is no earlier than the next
  candle open.
- Long-only execution: BUY enters, SELL exits; SELL does not open a short.
- Compare against cost-aware buy-and-hold and a cash-only baseline (0% return,
  0% drawdown, zero trades).
- No leverage, funding, partial fills, market impact, or claim of profitability.

For the primary validation run, keep fee/slippage at the registered defaults.
Sensitivity runs must be labeled separately and cannot replace the primary
run. Do not tune parameters against these windows and then present their results
as an unbiased estimate of the selected candidate's performance.

## Data integrity and source failures

Each matrix job must verify the complete requested range, candle count,
timestamp ordering, uniqueness, interval continuity, OHLC validity, and source
provenance before evaluating the strategy. Never sort malformed source rows
into apparent validity, silently drop gaps, interpolate candles, or combine
sources to conceal a gap. A source may be retried or replaced only by a source
that independently provides a complete, internally consistent requested range.
Record all failed source attempts in workflow logs. If no source provides a
complete range, fail the job and report it as an acquisition failure—not a
strategy result.

## Reproducibility and acceptance

The workflow stores normalized CSV data, SHA-256 manifest, complete JSON
report, and summary as 90-day artifacts. Every report must identify the exact
code commit, interval, UTC range, accepted source, dataset hash, fee/slippage,
and strategy/benchmark metrics. Data are not committed to Git.

Before calling the validation matrix complete:
- [ ] All six existing validation combinations finish and artifacts are present.
- [ ] Every dataset's count, boundaries, continuity, source URL, and SHA-256 are checked.
- [ ] Strategy return, drawdown, trade count, win rate, profit factor, exposure,
      and average trade metrics are reviewed for every window.
- [ ] Results are compared with cost-aware buy-and-hold and cash-only baseline.
- [ ] Failed/missing jobs are documented and rerun; no window is silently omitted.
- [ ] The evaluated commit and all artifact links are recorded in the PR.
- [ ] No weights/thresholds were tuned against these windows after their
      validation results were inspected.

Before the reserved final test:
- [ ] Both collaborators explicitly agree to the candidate commit and reserved
      date range before the dataset is downloaded or results are viewed.
- [ ] Confirm the proposed final-test period has not been used for candidate
      selection; otherwise choose a later untouched period.
- [ ] Freeze fees, slippage, signal parameters, execution rules, and metrics.
- [ ] Run the final-test candidate once and report all results, including
      negative or inconclusive outcomes. Do not tune against the final test.

A green unit-test workflow or a successful single-window smoke test does not
satisfy either gate. Any parameter changes after the final test require a new
strategy version and a new untouched evaluation period.

## Limitations

This is a research validation protocol, not investment advice or a promise of
future performance. The 24-bar forward-horizon diagnostic has overlapping
observations and is not fill-level PnL. Results remain sensitive to fees,
slippage, market microstructure, and the long-only assumption. Buy-and-hold is
a descriptive comparator, not a risk-adjusted benchmark by itself.
