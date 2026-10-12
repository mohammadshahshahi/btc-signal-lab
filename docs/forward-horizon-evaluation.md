# Forward Horizon Evaluation Contract (v1.0)

## Purpose

The forward-horizon evaluator measures whether signal directions align with
the price move over a fixed number of future candles. The default is 24 bars;
for BTCUSDT 1h data this represents a 24-hour horizon.

## Anti-look-ahead rule

For a signal formed at candle index i close, the signal function receives only
candles 0 through i. The outcome is measured from close[i] to
close[i + horizon_bars]. The future candle is used only to score the already
formed signal and is never passed to the signal function.

## Metrics

- Directional accuracy: correct LONG/SHORT outcomes divided by all actionable
  LONG/SHORT signals. NEUTRAL signals are excluded.
- Coverage: actionable LONG/SHORT signals divided by all evaluated signals.
- Long hit rate: share of LONG signals followed by a return above the neutral band.
- Short hit rate: share of SHORT signals followed by a return below the negative
  neutral band.
- Mean directional return: raw forward return for LONG and its negation for SHORT.
- Each observation stores signal/target indices, timestamps, closes, direction,
  score, forward return, and hit result.

The optional neutral band is expressed in percentage points and defaults to
zero. A forward move inside the band is not a successful directional hit.

## Limitations

This is a directional forecasting diagnostic, not a fill-level trading
simulation or net PnL. It excludes fees, slippage, spread, funding, and market
impact. Adjacent 24-bar outcomes overlap and are not independent observations.
Use multiple market regimes and a predeclared out-of-sample period before
drawing conclusions. The score is not a probability.
