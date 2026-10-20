"""Research-only classification of data gaps against source-backed venue outages.

This module never turns an incomplete candle series into a valid series. A known
outage remains ineligible under strict continuous-candle validation.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable


def _parse_utc(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("timestamp must be an ISO-8601 UTC string ending in Z")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed


def classify_gap(
    gap_start_utc: str,
    gap_end_utc: str,
    *,
    venue: str,
    symbol: str,
    events: Iterable[dict[str, Any]],
    mode: str = "strict",
) -> dict[str, Any]:
    """Classify [gap_start, gap_end) without ever approving missing candles.

    In strict mode every gap is rejected. In explicit outage_aware mode, a gap
    fully contained by a matching, source-backed event is marked excluded; it
    is still not valid data.
    """
    if mode not in {"strict", "outage_aware"}:
        raise ValueError("mode must be 'strict' or 'outage_aware'")
    start, end = _parse_utc(gap_start_utc), _parse_utc(gap_end_utc)
    if end <= start:
        raise ValueError("gap_end_utc must be later than gap_start_utc")

    for event in events:
        try:
            event_start = _parse_utc(event["documented_suspension_start_utc"])
            event_end = _parse_utc(event["documented_resume_utc"])
            sources = event["sources"]
            if not isinstance(sources, list) or not sources:
                continue
            if not all(isinstance(source, dict) and isinstance(source.get("url"), str)
                       and source["url"].startswith("https://") for source in sources):
                continue
            venue_matches = event.get("venue") == venue
            scope = event.get("symbol_scope")
            symbol_matches = scope == "all Spot symbols per official announcement" or scope == symbol
            if venue_matches and symbol_matches and event_start <= start and end <= event_end:
                if mode == "strict":
                    return {
                        "eligible": False,
                        "status": "rejected_documented_outage_strict_mode",
                        "event_id": event.get("event_id", "unknown"),
                        "reason": "Strict continuous-candle validation does not permit missing candles, even during a documented outage.",
                    }
                return {
                    "eligible": False,
                    "status": "excluded_documented_outage",
                    "event_id": event.get("event_id", "unknown"),
                    "reason": "Window overlaps a source-backed venue halt and is not eligible for continuous-candle calculations.",
                }
        except (KeyError, TypeError, ValueError):
            continue

    return {
        "eligible": False,
        "status": "rejected_unexplained_gap",
        "event_id": None,
        "reason": "No valid source-backed outage event fully contains this gap; fail closed.",
    }
