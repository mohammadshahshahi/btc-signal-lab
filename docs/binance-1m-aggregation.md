# Strict Binance Spot 1m archive aggregation

## Scope

This is a same-venue fallback for already-registered historical **validation** windows only. It derives 1h, 4h, or 1d BTCUSDT Spot candles from Binance Vision monthly 1m ZIP archives when native-interval sources cannot provide a complete range. It is not enabled for the reserved final-test period.

## Fail-closed input contract

- The requested start and end are UTC target-candle boundaries; end is exclusive.
- Every source 1m row is checked in original source order. Timestamps must be strictly increasing, unique, and exactly 60,000 ms apart.
- Every OHLC value must be finite and positive; volume must be finite and non-negative; OHLC relationships must be valid.
- The full requested minute range must be present, including the first and final minute.
- No interpolation, forward-fill, fabricated no-trade candle, row dropping, sorting, or cross-provider stitching is permitted.
- Any missing, duplicate, out-of-order, malformed, or partial minute rejects the entire derived dataset.

## Aggregation formula

For each UTC-aligned target bucket:

| Target | Required 1m constituents |
|---|---:|
| 1h | 60 |
| 4h | 240 |
| 1d | 1,440 |

- Open = first constituent open
- High = maximum constituent high
- Low = minimum constituent low
- Close = last constituent close
- Volume = sum of constituent volumes

## Provenance

The dataset manifest retains the CSV SHA-256 and records:
- Source venue and 1m archive URLs
- SHA-256 of each downloaded ZIP archive
- Source and target intervals
- Aggregation formula
- Expected constituents per target candle
- Actual bucket count, minimum/maximum constituent count, and total constituents
- Exact UTC range

## Validation

Offline fixture tests cover exact aggregation, missing minute, duplicate, out-of-order input, invalid OHLCV, and incomplete final bucket. The multi-regime validation workflow tries native-interval sources first and invokes this same-venue fallback only after they fail strict validation. The six-window workflow must then be run manually and all manifests/artifacts reviewed. A green unit-test run alone does not establish that the real archive contains complete minute coverage.
