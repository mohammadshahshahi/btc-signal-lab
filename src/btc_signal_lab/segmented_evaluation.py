"""Explicitly segmented paper evaluation for datasets with missing time buckets.

This is an opt-in research helper. It never fills missing candles. Each contiguous
segment is evaluated independently so indicators warm up from that segment only,
positions are liquidated at segment end, and forward labels cannot cross gaps.
Segment returns are intentionally not compounded into a misleading global metric.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from .backtest import run_backtest
from .horizon_evaluator import evaluate_forward_horizon

Candle = Mapping[str, Any]


def split_contiguous_segments(
    candles: Sequence[Candle], *, interval_ms: int
) -> list[list[dict[str, Any]]]:
    """Split chronologically ordered candles wherever timestamp delta != interval.

    Timestamps must be integer epoch milliseconds. Duplicates and out-of-order
    candles are rejected instead of being silently sorted or deduplicated.
    """
    if not isinstance(candles, Sequence) or isinstance(candles, (str, bytes)):
        raise TypeError("candles must be a sequence")
    if isinstance(interval_ms, bool) or not isinstance(interval_ms, int) or interval_ms <= 0:
        raise ValueError("interval_ms must be a positive integer")
    if not candles:
        raise ValueError("candles must not be empty")

    segments: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    previous_ts: int | None = None
    for index, candle in enumerate(candles):
        if not isinstance(candle, Mapping):
            raise TypeError(f"candle[{index}] must be a mapping")
        ts = candle.get("timestamp_ms")
        if isinstance(ts, bool) or not isinstance(ts, int):
            raise ValueError(f"candle[{index}].timestamp_ms must be integer epoch milliseconds")
        if previous_ts is not None:
            delta = ts - previous_ts
            if delta <= 0:
                raise ValueError("candles must be strictly increasing with no duplicate timestamps")
            if delta != interval_ms:
                segments.append(current)
                current = []
        current.append(dict(candle))
        previous_ts = ts
    if current:
        segments.append(current)
    return segments


def evaluate_contiguous_segments(
    candles: Sequence[Candle],
    *,
    interval_ms: int,
    initial_capital: float = 10_000.0,
    fee_rate: float = 0.001,
    slippage_bps: float = 5.0,
    horizon_bars: int = 24,
) -> dict[str, Any]:
    """Evaluate each uninterrupted segment independently; no cross-gap state.

    Backtests require at least two candles. Forward-horizon metrics are produced
    only for segments longer than horizon_bars. Every backtest starts with the
    same initial capital and is liquidated at its own segment end; results are
    reported per segment, not summed or compounded.
    """
    if isinstance(horizon_bars, bool) or not isinstance(horizon_bars, int) or horizon_bars < 1:
        raise ValueError("horizon_bars must be a positive integer")
    segments = split_contiguous_segments(candles, interval_ms=interval_ms)
    results: list[dict[str, Any]] = []
    for index, segment in enumerate(segments):
        result: dict[str, Any] = {
            "segment_index": index,
            "start_timestamp_ms": segment[0]["timestamp_ms"],
            "end_timestamp_ms": segment[-1]["timestamp_ms"],
            "candle_count": len(segment),
            "backtest": None,
            "forward_horizon": None,
            "eligibility": "eligible_contiguous_segment",
        }
        if len(segment) >= 2:
            result["backtest"] = run_backtest(
                segment,
                initial_capital=initial_capital,
                fee_rate=fee_rate,
                slippage_bps=slippage_bps,
            )
        else:
            result["eligibility"] = "ineligible_too_short_for_backtest"
        if len(segment) > horizon_bars:
            result["forward_horizon"] = evaluate_forward_horizon(
                segment, horizon_bars=horizon_bars
            )
        results.append(result)

    return {
        "schema_version": "1.0",
        "evaluation_mode": "explicit_contiguous_segments",
        "policy": {
            "synthetic_candles": False,
            "indicator_history_crosses_gap": False,
            "positions_cross_gaps": False,
            "forward_labels_cross_gaps": False,
            "capital_compounded_across_segments": False,
            "interval_ms": interval_ms,
            "horizon_bars": horizon_bars,
        },
        "segment_count": len(results),
        "total_candles": sum(item["candle_count"] for item in results),
        "segments": results,
        "limitations": [
            "Opt-in research helper; canonical strict validation remains unchanged.",
            "Each segment starts with independent initial capital; segment returns are not a continuous portfolio curve.",
            "Segments shorter than the requested forward horizon have no forward-horizon result.",
            "This output does not override source-backed outage eligibility or prove a trading edge.",
        ],
    }
