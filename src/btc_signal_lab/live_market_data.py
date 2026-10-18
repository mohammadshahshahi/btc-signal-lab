"""Strict recent closed-candle fetcher for current-market paper signals.

This path is deliberately independent of historical archive/backtest downloads.
It uses one venue (Binance Spot), never fabricates candles, and rejects stale,
gapped, malformed, or insufficient input. No credentials or order execution.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .market_data import INTERVAL_MS, normalize_klines

BINANCE_LIVE_KLINES_URL = "https://data-api.binance.vision/api/v3/klines"
SUPPORTED_INTERVALS = frozenset({"1m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d"})
MIN_SIGNAL_CANDLES = 50


def fetch_latest_closed_klines(
    symbol: str = "BTCUSDT",
    interval: str = "1h",
    *,
    limit: int = 120,
    now_ms: int | None = None,
    timeout: float = 10.0,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch contiguous, fresh, closed Binance candles and return provenance.

    The exchange's currently forming candle is discarded. By default at least
    50 closed candles are required for EMA50. Freshness is measured from the
    close time of the newest returned candle and limited to two intervals.
    """
    if not isinstance(symbol, str) or not symbol.strip() or not symbol.isalnum():
        raise ValueError("symbol must be an alphanumeric market symbol such as BTCUSDT")
    symbol = symbol.upper()
    if interval not in SUPPORTED_INTERVALS or interval not in INTERVAL_MS:
        raise ValueError(f"unsupported interval: {interval}")
    if isinstance(limit, bool) or not isinstance(limit, int) or not MIN_SIGNAL_CANDLES + 1 <= limit <= 1000:
        raise ValueError(f"limit must be an integer in [{MIN_SIGNAL_CANDLES + 1}, 1000]")
    if timeout <= 0 or not math.isfinite(timeout):
        raise ValueError("timeout must be finite and positive")

    observed_now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    if isinstance(observed_now_ms, bool) or not isinstance(observed_now_ms, int) or observed_now_ms <= 0:
        raise ValueError("now_ms must be a positive integer UTC epoch-millisecond timestamp")

    step = INTERVAL_MS[interval]
    query = urlencode({"symbol": symbol, "interval": interval, "limit": limit})
    request = Request(
        f"{BINANCE_LIVE_KLINES_URL}?{query}",
        headers={"User-Agent": "btc-signal-lab-paper-signal/0.1"},
    )
    with urlopen(request, timeout=timeout) as response:
        raw_bytes = response.read()
    payload = json.loads(raw_bytes.decode("utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"unexpected Binance kline response: {payload!r}")

    # Validate source order and interval alignment BEFORE calling normalize_klines,
    # whose historical-data contract sorts timestamps. Live ingestion must never
    # let that sorting conceal an upstream ordering/alignment defect.
    previous_open_ms = None
    for index, raw in enumerate(payload):
        if not isinstance(raw, (list, tuple)) or len(raw) < 6:
            raise ValueError(f"kline[{index}] must contain at least six fields")
        try:
            opened_ms = int(raw[0])
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"kline[{index}] has an invalid open timestamp") from exc
        if opened_ms % step != 0:
            raise ValueError(f"kline[{index}] timestamp {opened_ms} is not aligned to {interval}")
        if previous_open_ms is not None and opened_ms <= previous_open_ms:
            raise ValueError(
                f"provider timestamps are not strictly increasing at row {index}: "
                f"{previous_open_ms} -> {opened_ms}"
            )
        previous_open_ms = opened_ms

    normalized = normalize_klines(payload, 0, observed_now_ms + step, interval)
    closed = [row for row in normalized if row["timestamp_ms"] + step <= observed_now_ms]
    if len(closed) < MIN_SIGNAL_CANDLES:
        raise ValueError(
            f"insufficient closed candles: required at least {MIN_SIGNAL_CANDLES}, got {len(closed)}"
        )
    latest_close_ms = closed[-1]["timestamp_ms"] + step
    staleness_ms = observed_now_ms - latest_close_ms
    if staleness_ms < 0:
        raise ValueError("latest candle is not closed")
    if staleness_ms > 2 * step:
        raise ValueError(
            f"latest closed candle is stale by {staleness_ms} ms; maximum is {2 * step} ms"
        )

    # normalize_klines checks gaps among all in-range rows; also ensure enough
    # continuity remains after discarding the still-forming candle.
    expected = list(range(closed[0]["timestamp_ms"], closed[-1]["timestamp_ms"] + step, step))
    actual = [row["timestamp_ms"] for row in closed]
    if actual != expected:
        raise ValueError("closed candle window contains missing or misaligned timestamps")

    provenance = {
        "source": "Binance Spot public REST API",
        "source_url": f"{BINANCE_LIVE_KLINES_URL}?{query}",
        "symbol": symbol,
        "interval": interval,
        "observed_at_utc": datetime.fromtimestamp(observed_now_ms / 1000, timezone.utc).isoformat().replace("+00:00", "Z"),
        "latest_closed_candle_open_utc": closed[-1]["timestamp"],
        "latest_closed_candle_close_utc": datetime.fromtimestamp(latest_close_ms / 1000, timezone.utc).isoformat().replace("+00:00", "Z"),
        "closed_candle_count": len(closed),
        "staleness_ms": staleness_ms,
        "response_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "live_orders_submitted": 0,
    }
    return closed, provenance
