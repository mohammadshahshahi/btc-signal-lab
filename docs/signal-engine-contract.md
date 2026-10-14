# Signal Engine Contract (v1.1)

## Scope and safety

This component computes technical indicators and a deterministic research signal.
It is **paper-trading only**: it does not connect to an exchange, place orders,
manage funds, or read/store exchange credentials. BUY/SELL are labels in an
analysis result, not execution instructions or claims of profitability.

## Input

Call `generate_signal(candles, symbol="BTC/USDT", timeframe="1h")`.

- `candles` is a non-empty chronological sequence, oldest first.
- Each candle must contain numeric, finite `high`, `low`, and `close`.
- `high >= low` and `low <= close <= high` are required.
- Timestamps and open prices are intentionally not required by this first contract.
- Missing history is not fabricated; indicators remain `null` until warmed up.

## Output JSON

```json
{
  "schema_version": "1.1",
  "mode": "paper_trading",
  "symbol": "BTC/USDT",
  "timeframe": "1h",
  "signal": "HOLD",
  "direction": "NEUTRAL",
  "score": 50.0,
  "score_components": {
    "trend": 0.0,
    "price_vs_ema20": 0.0,
    "macd_momentum": 0.0,
    "rsi_momentum": 0.0
  },
  "score_thresholds": {"long": 70.0, "short": 30.0},
  "price": 100.0,
  "indicators": {
    "ema20": null,
    "ema50": null,
    "rsi14": null,
    "macd": null,
    "macd_signal": null,
    "macd_histogram": null,
    "atr14": null,
    "volume_sma20": null,
    "volume_ratio": null
  },
  "reasons": ["insufficient_history"]
}
```

The example shows the shape, not a promise that every field is null for every
short input. Indicator values are finite JSON numbers or `null`; NaN and
Infinity are never emitted. `to_json` emits deterministic compact JSON.

## Indicator conventions

- EMA: seed with the SMA of the first `period` closes; then use
  `alpha = 2 / (period + 1)`.
- RSI14: Wilder smoothing of positive and negative close-to-close changes;
  flat data yields 50, gains-only yields 100, losses-only yields 0.
- MACD: EMA(12) minus EMA(26), signal EMA(9) of valid MACD values, histogram
  MACD minus signal. Component EMAs use the same SMA seed.
- ATR14: Wilder smoothing of true range, seeded with the first 14 true ranges;
  the first candle's true range is high minus low.
- Optional volume metrics: when volume is present on every candle, report the
  20-candle simple moving average and latest-volume / average-volume ratio.
  Volume is not required by v1.0 callers and is not a directional signal by itself.

## Continuous directional score

The v1.1 score is a deterministic technical-strength index in [0, 100], not a
probability or calibrated confidence estimate. A score of 50 is neutral.
Insufficient indicator history returns score 50 and HOLD/NEUTRAL.

Each component is bounded to [-1, 1] and normalized by ATR where applicable:

- trend = tanh(4 * (EMA20 - EMA50) / ATR14)
- price_vs_ema20 = tanh(2 * (close - EMA20) / ATR14)
- macd_momentum = tanh(20 * (MACD - MACD_signal) / ATR14)
- rsi_momentum = clamp((RSI14 - 50) / 20, -1, 1)

The directional composite is 35% trend, 20% price_vs_ema20, 25%
macd_momentum, and 20% rsi_momentum. The final score is
clamp(50 + 50 * composite, 0, 100). Volume ratio is reported as context but
does not independently determine direction. ATR is a volatility scale, not a
bullish or bearish input.

- score >= 70: signal BUY, direction LONG.
- score <= 30: signal SELL, direction SHORT.
- otherwise: signal HOLD, direction NEUTRAL.

BUY/SELL/HOLD are retained for compatibility with the paper simulator;
LONG/SHORT/NEUTRAL are explicit direction aliases for reporting and analysis.
These thresholds and weights are an initial heuristic baseline, not a
validated strategy. No probability or profitability claim is implied.

## Compatibility and collaboration

The implementation adds a self-contained module under `src/btc_signal_lab/`
and tests under `tests/`; it does not modify the existing README or other shared
files. Before merging, align this schema and rule set with Saeed and Mohammad.
