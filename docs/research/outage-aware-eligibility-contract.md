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
