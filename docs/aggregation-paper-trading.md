# Signal Aggregation and Paper Trading Contract (v1.0)

## Signal vocabulary

This repository's current Signal Engine v1.0 emits `BUY`, `SELL`, and
`HOLD`. Aggregation and simulation preserve these labels. They are research
labels only and never trigger exchange orders.

## Five-snapshot aggregation

`aggregate_signals(signals)` accepts timestamped snapshots, oldest first or
in arbitrary order. Timestamps must be unique timezone-aware ISO-8601 values.
Only the five most recent snapshots are retained. Recency weights, newest
first, are 40%, 25%, 15%, 12%, and 8%; weights are renormalized when fewer
than five snapshots exist.

A supplied numeric `score` must be finite and within [0, 100]. For compatibility
with Signal Engine v1.0, a snapshot without a score maps BUY/HOLD/SELL to
100/50/0. The weighted score maps to BUY at >=70, SELL at <=30, otherwise HOLD.
The output includes both the compatibility action label (BUY/SELL/HOLD) and
the direction alias (LONG/SHORT/NEUTRAL). It records its 24-hour intended
horizon. The score is a technical-strength index, not a calibrated probability
or a guarantee of future performance.

## Paper trading

`PaperTrader` is an in-memory, all-in/all-out, long-only spot simulator.
BUY opens only when flat; SELL closes only an open long; HOLD has no effect.
It applies adverse fixed slippage and fees on entry and exit. It does not model
short positions, partial fills, spread, market impact, funding, or exchange
execution. The caller must supply the simulated fill price; for historical
simulation this should be no earlier than the next candle open after a signal.

The snapshot reports `live_orders_submitted: 0`. No API client, credentials,
network access, or live order functionality exists in this module. Persistence
and scheduled orchestration are handled separately.
