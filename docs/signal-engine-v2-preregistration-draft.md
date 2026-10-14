# Signal Engine v2 — Research Pre-registration (Draft for Joint Approval)

**Status:** draft only; not approved for experiments.  
**Related:** Issue #13 (v2 research plan), Issue #2 (data partition and exposure gate), PR #14 (v1.1 baseline).  
**Safety:** paper research only. No exchange credentials, real orders, leverage, or live trading.

This document is a proposed protocol for review by Muhammad and Saeed. It does not authorize downloading any reserved final-test data or starting a parameter search. Experiments begin only after both contributors approve this exact document and Issue #2's data policy.

## 1. Research question and hypotheses

**Primary question:** Can a simple, interpretable BTCUSDT Spot trend/momentum strategy improve risk-adjusted, after-cost performance over frozen v1.1 and passive/cash benchmarks across chronological development/validation folds?

Pre-registered hypotheses:
- H1 (risk control): requiring a higher-timeframe trend regime before taking a long entry may reduce maximum drawdown and time spent exposed during adverse regimes.
- H2 (trade quality): a modest momentum confirmation at entry may reduce low-quality entries and turnover without eliminating too much upside participation.
- H3 (robustness): any apparent improvement should persist across multiple chronological folds and under a higher transaction-cost stress case; a single strong window is insufficient.

These are falsifiable research hypotheses, not claims that v2 will outperform.

## 2. Frozen comparator and execution assumptions

- Comparator A: Signal Engine v1.1 exactly as documented in `docs/signal-engine-v1.1-baseline.md`; no parameter changes.
- Comparator B: cost-aware BTCUSDT Spot buy-and-hold over identical timestamps.
- Comparator C: flat cash/no trade.
- Comparator D: simple trend baseline, long when close > EMA(200), otherwise cash; signal at close, fill no earlier than next bar open.
- Initial capital: 10,000 quote-currency units.
- Primary costs: fee 0.10% per side plus slippage 5 bps per side.
- Stress costs: fee 0.15% per side plus slippage 10 bps per side.
- Spot, long-only, no leverage, no funding, no partial fills, no market-impact model.
- All strategies use the same candle timestamps, fill convention, and cost accounting.

## 3. Candidate v2 design and bounded search space

Keep the first v2 experiment intentionally small and interpretable. Do not introduce machine learning, dozens of indicators, or unbounded optimization.

Candidate structure:
1. Trend gate: close above EMA(100) OR EMA(200) (2 choices).
2. Entry momentum gate: RSI(14) >= 50 OR RSI(14) >= 55 (2 choices).
3. Exit rule: close below EMA(20) OR RSI(14) < 45 (2 choices).

This yields at most 8 pre-registered combinations. The indicator definitions and warm-up handling must be specified in code/tests before the first fold is run. No additional parameter values may be added after viewing fold results. v1.1 remains a separate immutable comparator.

## 4. Development and validation data policy

Known exposed evidence:
- All inspected 2021–2025 windows, including the five successful run #21 windows and January 2025 smoke test, are exposed. They may be described but must not be used to select v2 parameters or claim unbiased generalization.
- Recovery/1h is unavailable from tested sources and must remain unavailable unless a separately sourced complete dataset passes independent provenance and continuity review.
- No retrospective relabelling of previously inspected data.

Proposed initial development period: BTCUSDT Spot from the earliest complete, verified Binance history available through 2021-10-31 23:00 UTC. The exact start timestamp, row counts, source provenance, and hashes must be recorded before running any candidate.

Proposed rolling-origin folds within that pre-exposed period:
- For each timeframe independently, use expanding chronological training history with a 6-month validation block.
- Require at least 24 months of training history before the first validation block.
- Advance the validation origin by 6 months per fold; no random shuffling.
- Apply a purge/embargo of at least 24 bars on each train/validation boundary for any 24-bar forward-horizon diagnostics. For fill-level portfolio PnL, preserve next-bar execution and ensure no trade/label state crosses a fold boundary.
- Exact fold dates and expected candle counts must be computed from UTC boundaries and committed before data acquisition.

The 2025-02-01 through 2026-02-01 candidate holdout remains sealed. It is not a validation set by default. Before any access, both contributors must independently attest YES/NO/UNSURE to prior exposure and approve exact partition roles. If either answer is YES or UNSURE, or approval is absent, do not call it untouched; choose a later future holdout or explicitly classify it as exposed. No test workflow should exist in an enabled/scheduled state before that gate.

## 5. Selection objective and rejection criteria

Primary selection statistic: median net Sharpe ratio across validation folds, calculated from a clearly specified periodic equity-return series after costs. Also report fold dispersion and the number of folds with positive net return. Do not optimize raw cumulative return alone.

A candidate is rejected if any of the following applies:
- Median validation net Sharpe is not greater than both v1.1 and the EMA(200) trend baseline.
- Fewer than two-thirds of validation folds have positive net return.
- Median max drawdown exceeds 30%, or any fold exceeds 40%.
- The candidate loses its relative advantage under the stress-cost case.
- Performance depends on one fold, one regime, a small number of trades, or a single parameter corner.
- Any leakage, timestamp defect, non-determinism, or unregistered parameter change is found.

A candidate is not accepted solely because net return is positive. If no candidate passes all criteria, record v2 as rejected/inconclusive rather than widening the search after seeing results.

## 6. Required reporting

For every fold, candidate, timeframe, and cost case, report:
- Net return and final equity.
- Maximum drawdown and annualized volatility.
- Sharpe and Sortino with documented periodicity and risk-free-rate convention.
- Trade count, win rate, profit factor, average trade return and holding duration.
- Market exposure, turnover, fee and slippage totals.
- Buy-and-hold, flat-cash, EMA(200) trend baseline, and v1.1 comparators.
- Fold-level dispersion, median, interquartile range, and positive-fold count.
- Dataset URL/source, symbol, timeframe, exact UTC boundaries, row count, CSV SHA-256, retrieval timestamp, code commit, config hash, and protocol version.

## 7. Leakage and reproducibility controls

- All splits are chronological and generated from frozen UTC boundaries.
- Indicators are causal and calculated only from current/past bars.
- Signals at candle close execute no earlier than the next candle open.
- No centered rolling windows, future joins, backward filling, or use of final-test statistics.
- Validate timestamp uniqueness, strict ordering, interval continuity, OHLC consistency, and manifest hash before evaluation.
- Freeze the candidate grid, objective, rejection criteria, costs, and fold boundaries before the first experiment.
- Store immutable config JSON and hash, dataset manifests, commit SHA, deterministic report JSON, and CI results.
- Unit tests must cover split boundaries, purge/embargo, look-ahead fixtures, deterministic reruns, benchmark alignment, and cost accounting.

## 8. Approval checklist

- [ ] Muhammad approves the hypotheses, bounded candidate grid, objective, rejection criteria, costs, metrics, and fold design.
- [ ] Saeed approves data provenance, exact UTC split construction, purge/embargo implementation, reproducibility and CI controls.
- [ ] Both contributors explicitly attest YES/NO/UNSURE on prior exposure to 2025-02-01 through 2026-02-01.
- [ ] Both contributors approve whether that period is eligible as an untouched final test. If either answer is YES/UNSURE, select a later holdout or downgrade its status.
- [ ] Exact fold boundaries and expected candle counts are generated and committed before any permitted development/validation data acquisition.
- [ ] No v2 parameter search begins before the above approvals.

**Until every applicable approval is recorded, this remains a proposal only.**
