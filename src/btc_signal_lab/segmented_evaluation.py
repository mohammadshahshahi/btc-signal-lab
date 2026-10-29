"""Explicitly segmented paper evaluation for source-backed exchange outages.

This is an opt-in research helper. It never fills missing candles. Every gap must
be fully covered by a source-backed outage event matching venue, market, and
symbol scope. Each contiguous segment is evaluated independently so indicators
warm up from that segment only, positions are liquidated at segment end, and
forward labels cannot cross gaps. Segment returns are not compounded globally.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from .backtest import run_backtest
from .horizon_evaluator import evaluate_forward_horizon
from .benchmark import run_buy_and_hold
from .outage_policy import classify_gap

Candle = Mapping[str, Any]


def _epoch_ms_iso(timestamp_ms: int) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def split_contiguous_segments(
    candles: Sequence[Candle], *, interval_ms: int
) -> list[list[dict[str, Any]]]:
    """Split chronologically ordered candles wherever timestamp delta != interval.

    This low-level utility only partitions rows; it does not certify that a gap
    is legitimate. Use evaluate_contiguous_segments for guarded evaluation.
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
    venue: str,
    market: str,
    symbol: str,
    outage_events: Sequence[dict[str, Any]],
    initial_capital: float = 10_000.0,
    fee_rate: float = 0.001,
    slippage_bps: float = 5.0,
    horizon_bars: int = 24,
) -> dict[str, Any]:
    """Evaluate segments only when every gap is explained by a matching event.

    Backtests require at least two candles. Forward-horizon metrics are produced
    only for segments longer than horizon_bars. Every backtest starts with the
    same initial capital and is liquidated at its own segment end; results are
    reported per segment, not summed or compounded. Unexplained gaps raise.
    """
    if isinstance(horizon_bars, bool) or not isinstance(horizon_bars, int) or horizon_bars < 1:
        raise ValueError("horizon_bars must be a positive integer")
    if not isinstance(outage_events, Sequence) or isinstance(outage_events, (str, bytes)):
        raise TypeError("outage_events must be a sequence of source-backed events")
    segments = split_contiguous_segments(candles, interval_ms=interval_ms)

    # Record only events that actually explain an observed gap; do not list every
    # supplied candidate event in the output manifest.
    matched_event_ids: set[str] = set()

    # Validate all gap intervals before producing any evaluation results.
    for left, right in zip(candles, candles[1:]):
        left_ts, right_ts = left["timestamp_ms"], right["timestamp_ms"]
        if right_ts - left_ts == interval_ms:
            continue
        gap_start = _epoch_ms_iso(left_ts + interval_ms)
        gap_end = _epoch_ms_iso(right_ts)
        decision = classify_gap(
            gap_start, gap_end, venue=venue, market=market, symbol=symbol,
            events=outage_events, mode="outage_aware",
        )
        if decision["status"] != "excluded_documented_outage":
            raise ValueError(
                f"unexplained or unapproved data gap [{gap_start}, {gap_end}); "
                "segmented evaluation fails closed"
            )
        event_id = decision.get("event_id")
        if isinstance(event_id, str) and event_id and event_id != "unknown":
            matched_event_ids.add(event_id)

    results: list[dict[str, Any]] = []
    for index, segment in enumerate(segments):
        result: dict[str, Any] = {
            "segment_index": index,
            "start_timestamp_ms": segment[0]["timestamp_ms"],
            "end_timestamp_ms": segment[-1]["timestamp_ms"],
            "candle_count": len(segment),
            "backtest": None,
            "benchmark": None,
            "comparison": None,
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
            result["benchmark"] = run_buy_and_hold(
                segment,
                initial_capital=initial_capital,
                fee_rate=fee_rate,
                slippage_bps=slippage_bps,
            )
            result["comparison"] = {
                "strategy_minus_buy_and_hold_return_pct": (
                    result["backtest"]["net_return_pct"]
                    - result["benchmark"]["net_return_pct"]
                ),
                "interpretation": "per-segment descriptive comparison; not a continuous compounded portfolio result",
            }
        else:
            result["eligibility"] = "ineligible_too_short_for_backtest"
        if len(segment) > horizon_bars:
            result["forward_horizon"] = evaluate_forward_horizon(
                segment, horizon_bars=horizon_bars
            )
        results.append(result)

    return {
        "schema_version": "1.1",
        "evaluation_mode": "explicit_contiguous_segments",
        "outage_policy": {
            "mode": "outage_aware",
            "venue": venue,
            "market": market,
            "symbol": symbol,
            "matched_event_ids": sorted(matched_event_ids),
        },
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
            "Every gap must match a source-backed outage event; unexplained gaps fail closed.",
            "Each segment starts with independent initial capital; segment returns are not a continuous portfolio curve.",
            "Segments shorter than the requested forward horizon have no forward-horizon result.",
            "This output does not prove a trading edge.",
        ],
    }
