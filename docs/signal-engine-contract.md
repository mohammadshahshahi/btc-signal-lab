# Signal Engine Contract (v1.0)

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
  "schema_version": "1.0",
  "mode": "paper_trading",
  "symbol": "BTC/USDT",
  "timeframe": "1h",
  "signal": "HOLD",
  "price": 100.0,
  "indicators": {
    "ema20": null,
    "ema50": null,
    "rsi14": null,
    "macd": null,
    "macd_signal": null,
    "macd_histogram": null,
    "atr14": null
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

## Baseline signal rules

- BUY: close > EMA20 > EMA50, MACD > signal, histogram > 0, RSI in [50, 70].
- SELL: close < EMA20 < EMA50, MACD < signal, histogram < 0, RSI in [30, 50].
- HOLD: all other cases, including insufficient indicator history.

The rules are deliberately conservative and transparent. They are an initial
baseline to review with the collaborators, not a validated trading strategy.
No backtest or profitability claim is implied.

## Compatibility and collaboration

The implementation adds a self-contained module under `src/btc_signal_lab/`
and tests under `tests/`; it does not modify the existing README or other shared
files. Before merging, align this schema and rule set with Saeed and Mohammad.
