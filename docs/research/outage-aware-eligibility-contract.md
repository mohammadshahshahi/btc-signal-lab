# Source-backed outage-aware eligibility contract (proposal)

**Status:** isolated proposal; not wired into canonical candle aggregation or evaluation.  
**Default:** strict mode. Missing minutes remain a validation failure.

## Event semantics

Events describe a venue suspension as a half-open UTC interval [start, resume). A missing-candle interval is also represented as [gap_start, gap_end). A gap may be classified as a documented outage only if it is fully contained in a valid event whose venue, market, and symbol scope match and whose source list contains valid HTTPS URLs with hostnames. The broad symbol scope is represented explicitly as `all_spot_symbols`.

The initial evidence record is `binance-spot-halt-2023-03-24`: Binance Spot suspended trading at 11:27 UTC and resumed at 14:00 UTC on 2023-03-24. Official source links and BTCUSDT trade-archive SHA-256 are in `binance-spot-outage-2023-03-24.json`.

## Required behavior

- Strict mode rejects every missing-candle interval, including documented outages.
- Explicit outage-aware mode may label a fully contained, source-backed gap as `excluded_documented_outage`; it does not make the data complete or eligible for continuous-candle calculations.
- Unexplained gaps, invalid event intervals, invalid provenance, mismatched venue/market/symbol, invalid gap intervals, and gaps extending beyond event boundaries fail closed.
- Never synthesize, interpolate, forward-fill, or silently substitute candles or venues.
- No production validator or evaluation workflow consumes this proposal yet. Integration requires review, manifest changes, and end-to-end tests.
- The reserved final-test period 2025-02-01 through 2026-02-01 must remain untouched.

## Validation

`tests/test_outage_policy.py` covers strict rejection, explicit exclusion, event boundaries, provenance, symbol/venue mismatch, invalid event/gap intervals, and unknown modes. Passing these unit tests validates only this helper—not the production candle validator or strategy.

## Opt-in segmented research evaluator

The isolated helper in `src/btc_signal_lab/segmented_evaluation.py` implements a narrow research-only path without changing the default validator:

- `evaluate_contiguous_segments(...)` checks each observed timestamp gap with `classify_gap(..., mode="outage_aware")` before running any segment; one unexplained gap aborts the evaluation.
- A validated discontinuity splits the candles into separate contiguous segments. Each segment starts with independent initial capital, indicators warm up only within that segment, and the backtest is liquidated at that segment's end. Results are per-segment and must not be interpreted as one compounded equity curve.
- Forward-horizon evaluation receives only the candles from its own segment, so a label cannot borrow observations across a gap. No missing rows are generated.
- The output records `evaluation_mode=explicit_contiguous_segments`, policy flags, segment boundaries/counts, and `outage_policy.matched_event_ids`. That list contains only event IDs that actually matched observed gaps; it is not a dump of all candidate events supplied to the evaluator. The linked evidence JSON remains the source of official URLs and raw-archive SHA-256.
- Segments shorter than two candles are marked ineligible for backtesting; segments not longer than the requested forward horizon have no forward-horizon result.

This helper is not wired into canonical validation, benchmark dataset loading, or Multi-Regime Paper Validation. Its unit tests and historical paper-backtest CI are necessary but not sufficient for production adoption. Before integration, add a reviewed invocation path, a durable run-manifest schema with policy/evidence provenance, and an end-to-end test proving the production workflow cannot cross segment boundaries. Keep the default strict gate unchanged until that review is complete.
