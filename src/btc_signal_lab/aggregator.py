"""Weighted aggregation of the five most recent BTC signal snapshots.

The module is deterministic and independent of market-data/network clients.
Signal vocabulary follows signal_engine.py: BUY, SELL, HOLD.
"""
from __future__ import annotations

from datetime import datetime
from math import isfinite
from typing import Any, Mapping, Sequence

RECENCY_WEIGHTS = (0.40, 0.25, 0.15, 0.12, 0.08)
LABEL_SCORES = {"BUY": 100.0, "HOLD": 50.0, "SELL": 0.0}


def _timestamp(value: Any, index: int) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"signals[{index}].timestamp must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"signals[{index}].timestamp must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"signals[{index}].timestamp must include a timezone")
    return parsed


def _score(item: Mapping[str, Any], index: int) -> float:
    if "score" in item:
        value = item["score"]
        if isinstance(value, bool):
            raise ValueError(f"signals[{index}].score must be numeric")
        try:
            score = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"signals[{index}].score must be numeric") from exc
        if not isfinite(score) or not 0.0 <= score <= 100.0:
            raise ValueError(f"signals[{index}].score must be finite and in [0, 100]")
        return score
    label = item.get("signal")
    if label not in LABEL_SCORES:
        raise ValueError(f"signals[{index}].signal must be BUY, SELL, or HOLD")
    return LABEL_SCORES[label]


def aggregate_signals(signals: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate up to five recent snapshots, renormalizing available weights.

    Inputs may contain a numeric score in [0, 100]. For compatibility with
    signal_engine v1.0, snapshots without a score map BUY/HOLD/SELL to
    100/50/0 respectively. The newest snapshot receives the largest weight.
    """
    if not isinstance(signals, Sequence) or isinstance(signals, (str, bytes)):
        raise TypeError("signals must be a sequence of signal mappings")
    if not signals:
        raise ValueError("at least one signal is required")

    normalized: list[tuple[datetime, float, str]] = []
    for i, item in enumerate(signals):
        if not isinstance(item, Mapping):
            raise TypeError(f"signals[{i}] must be a mapping")
        if "timestamp" not in item:
            raise ValueError(f"signals[{i}] is missing timestamp")
        stamp = _timestamp(item["timestamp"], i)
        score = _score(item, i)
        label = item.get("signal", "SCORED")
        normalized.append((stamp, score, str(label)))

    normalized.sort(key=lambda row: row[0])
    stamps = [row[0] for row in normalized]
    if len(set(stamps)) != len(stamps):
        raise ValueError("signal timestamps must be unique")

    recent = normalized[-len(RECENCY_WEIGHTS):]
    weights = RECENCY_WEIGHTS[:len(recent)]
    total_weight = sum(weights)
    weighted_score = sum(
        row[1] * weight for row, weight in zip(reversed(recent), weights)
    ) / total_weight

    if weighted_score >= 70.0:
        decision = "BUY"
    elif weighted_score <= 30.0:
        decision = "SELL"
    else:
        decision = "HOLD"

    direction = {"BUY": "LONG", "SELL": "SHORT", "HOLD": "NEUTRAL"}[decision]
    return {
        "schema_version": "1.1",
        "signal": decision,
        "direction": direction,
        "score": round(weighted_score, 6),
        "score_thresholds": {"long": 70.0, "short": 30.0},
        "sample_count": len(recent),
        "weights": [round(weight / total_weight, 8) for weight in weights],
        "window_start": recent[0][0].isoformat(),
        "window_end": recent[-1][0].isoformat(),
        "source_signals": [row[2] for row in reversed(recent)],
        "horizon": "24h",
    }
