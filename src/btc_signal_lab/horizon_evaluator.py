"""Leakage-aware forward-horizon evaluation for timestamped signal snapshots.

A signal at candle close i is scored against close i + horizon_bars.
Only candles through i are passed to the signal function. This module reports
directional research metrics; it does not simulate fills or claim profitability.
"""
from __future__ import annotations

from math import isfinite
from typing import Any, Callable, Mapping, Sequence

from .signal_engine import generate_signal

Candle = Mapping[str, Any]
SignalFunction = Callable[[Sequence[Candle]], Mapping[str, Any]]
DIRECTION_MAP = {"BUY": "LONG", "SELL": "SHORT", "HOLD": "NEUTRAL"}


def _positive_close(candle: Candle, index: int) -> float:
    if not isinstance(candle, Mapping):
        raise TypeError(f"candle[{index}] must be a mapping")
    if "close" not in candle:
        raise ValueError(f"candle[{index}] is missing close")
    value = candle["close"]
    if isinstance(value, bool):
        raise ValueError(f"candle[{index}].close must be numeric")
    try:
        close = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"candle[{index}].close must be numeric") from exc
    if not isfinite(close) or close <= 0:
        raise ValueError(f"candle[{index}].close must be finite and positive")
    return close


def evaluate_forward_horizon(
    candles: Sequence[Candle],
    *,
    horizon_bars: int = 24,
    neutral_band_pct: float = 0.0,
    signal_fn: SignalFunction | None = None,
) -> dict[str, Any]:
    """Evaluate signal direction against the close after a fixed bar horizon.

    At each eligible index i, signal_fn receives candles[:i+1] only. The
    outcome is measured from close[i] to close[i+horizon_bars]. LONG is a hit
    only above the neutral band; SHORT is a hit only below its negative.
    NEUTRAL signals are excluded from directional accuracy and counted
    separately. No fees, fills, or trade PnL are simulated here.
    """
    if not isinstance(candles, Sequence) or isinstance(candles, (str, bytes)):
        raise TypeError("candles must be a sequence")
    if isinstance(horizon_bars, bool) or not isinstance(horizon_bars, int) or horizon_bars < 1:
        raise ValueError("horizon_bars must be a positive integer")
    if isinstance(neutral_band_pct, bool):
        raise ValueError("neutral_band_pct must be numeric")
    try:
        band = float(neutral_band_pct)
    except (TypeError, ValueError) as exc:
        raise ValueError("neutral_band_pct must be numeric") from exc
    if not isfinite(band) or band < 0:
        raise ValueError("neutral_band_pct must be finite and non-negative")
    if len(candles) <= horizon_bars:
        raise ValueError("at least horizon_bars + 1 candles are required")

    closes = [_positive_close(candle, i) for i, candle in enumerate(candles)]
    if signal_fn is None:
        signal_fn = generate_signal

    observations: list[dict[str, Any]] = []
    long_hits = long_count = short_hits = short_count = neutral_count = 0
    directional_returns: list[float] = []
    raw_returns: list[float] = []

    for index in range(len(candles) - horizon_bars):
        # Critical anti-leakage boundary: no candle after index is passed in.
        result = signal_fn(candles[: index + 1])
        if not isinstance(result, Mapping):
            raise TypeError("signal_fn must return a mapping")
        direction = result.get("direction")
        if direction is None:
            direction = DIRECTION_MAP.get(result.get("signal"))
        if direction not in {"LONG", "SHORT", "BEARISH", "NEUTRAL"}:
            raise ValueError(f"signal_fn returned unsupported direction: {direction!r}")

        target_index = index + horizon_bars
        forward_return_pct = (closes[target_index] / closes[index] - 1.0) * 100.0
        raw_returns.append(forward_return_pct)
        hit: bool | None
        if direction == "LONG":
            long_count += 1
            hit = forward_return_pct > band
            long_hits += int(hit)
            directional_returns.append(forward_return_pct)
        elif direction in {"SHORT", "BEARISH"}:
            short_count += 1
            hit = forward_return_pct < -band
            short_hits += int(hit)
            directional_returns.append(-forward_return_pct)
        else:
            neutral_count += 1
            hit = None

        observations.append({
            "signal_index": index,
            "target_index": target_index,
            "signal_timestamp": candles[index].get("timestamp"),
            "target_timestamp": candles[target_index].get("timestamp"),
            "direction": direction,
            "score": result.get("score"),
            "signal_close": closes[index],
            "target_close": closes[target_index],
            "forward_return_pct": round(forward_return_pct, 8),
            "directional_hit": hit,
        })

    actionable = long_count + short_count
    hits = long_hits + short_hits
    return {
        "schema_version": "1.0",
        "evaluation": "forward_directional_horizon",
        "horizon_bars": horizon_bars,
        "observation_count": len(observations),
        "actionable_count": actionable,
        "neutral_count": neutral_count,
        "coverage_pct": round(actionable / len(observations) * 100.0, 6),
        "directional_accuracy_pct": round(hits / actionable * 100.0, 6) if actionable else None,
        "long_count": long_count,
        "long_hit_rate_pct": round(long_hits / long_count * 100.0, 6) if long_count else None,
        "short_count": short_count,
        "short_hit_rate_pct": round(short_hits / short_count * 100.0, 6) if short_count else None,
        "neutral_band_pct": band,
        "mean_forward_return_pct": round(sum(raw_returns) / len(raw_returns), 8),
        "mean_directional_return_pct": (
            round(sum(directional_returns) / len(directional_returns), 8)
            if directional_returns else None
        ),
        "observations": observations,
        "limitations": [
            "Signals use candles through the signal candle close only; outcomes use the later horizon close.",
            "This is directional accuracy research, not a fill-level trading simulation or net PnL.",
            "Overlapping forward horizons are not independent observations.",
            "No fees, slippage, spread, funding, or market impact are included.",
            "A single historical window does not establish predictive power or future profitability.",
        ],
    }
