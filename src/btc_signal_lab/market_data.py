"""Public, credential-free Binance OHLCV download and dataset provenance helpers.

This module is opt-in and separate from signal generation/backtesting. It never
uses API keys and only downloads public spot candles.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlencode
from urllib.request import Request, urlopen

INTERVAL_MS = {"1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}
BINANCE_KLINES_URL = "https://data-api.binance.vision/api/v3/klines"
CSV_FIELDS = ["timestamp", "open", "high", "low", "close", "volume"]


def parse_utc(value: str) -> datetime:
    """Parse an ISO-8601 timestamp with an explicit timezone."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("timestamps must be ISO-8601 strings with timezone") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamps must include a timezone, for example Z")
    return parsed.astimezone(timezone.utc)


def normalize_klines(payload: Sequence[Sequence[Any]], start_ms: int, end_ms: int,
                     interval: str) -> list[dict[str, Any]]:
    """Validate and normalize Binance kline rows; range is [start_ms, end_ms)."""
    if interval not in INTERVAL_MS:
        raise ValueError(f"unsupported interval: {interval}")
    if not isinstance(payload, Sequence) or isinstance(payload, (str, bytes)):
        raise TypeError("kline payload must be a sequence")
    step = INTERVAL_MS[interval]
    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(payload):
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or len(raw) < 6:
            raise ValueError(f"kline[{index}] must contain at least six fields")
        try:
            opened = int(raw[0])
            values = [float(raw[i]) for i in (1, 2, 3, 4, 5)]
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"kline[{index}] contains invalid numeric data") from exc
        if not all(math.isfinite(v) for v in values):
            raise ValueError(f"kline[{index}] contains non-finite data")
        open_price, high, low, close, volume = values
        if min(open_price, high, low, close) <= 0 or volume < 0:
            raise ValueError(f"kline[{index}] has non-positive prices or negative volume")
        if high < low or not low <= open_price <= high or not low <= close <= high:
            raise ValueError(f"kline[{index}] has inconsistent OHLC values")
        if start_ms <= opened < end_ms:
            rows.append({
                "timestamp_ms": opened,
                "timestamp": datetime.fromtimestamp(opened / 1000, timezone.utc).isoformat().replace("+00:00", "Z"),
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            })
    rows.sort(key=lambda row: row["timestamp_ms"])
    timestamps = [row["timestamp_ms"] for row in rows]
    if len(set(timestamps)) != len(timestamps):
        raise ValueError("dataset contains duplicate candle timestamps")
    for previous, current in zip(timestamps, timestamps[1:]):
        if current - previous != step:
            raise ValueError(f"dataset has a candle gap between {previous} and {current}")
    return rows


def download_binance_klines(symbol: str, interval: str, start: str, end: str,
                            *, timeout: float = 30.0) -> list[dict[str, Any]]:
    """Download public candles for an explicit UTC interval, paginating at 1000 rows."""
    if not isinstance(symbol, str) or not symbol.strip() or not symbol.isalnum():
        raise ValueError("symbol must be an alphanumeric spot symbol such as BTCUSDT")
    if interval not in INTERVAL_MS:
        raise ValueError(f"supported intervals: {', '.join(INTERVAL_MS)}")
    start_dt, end_dt = parse_utc(start), parse_utc(end)
    start_ms, end_ms = int(start_dt.timestamp() * 1000), int(end_dt.timestamp() * 1000)
    step = INTERVAL_MS[interval]
    if end_ms <= start_ms:
        raise ValueError("end must be later than start")
    if start_ms % step or end_ms % step:
        raise ValueError(f"start and end must align to {interval} candle boundaries")

    raw_rows: list[Sequence[Any]] = []
    cursor = start_ms
    while cursor < end_ms:
        query = urlencode({
            "symbol": symbol.strip().upper(),
            "interval": interval,
            "startTime": cursor,
            "endTime": end_ms - 1,
            "limit": 1000,
        })
        request = Request(
            f"{BINANCE_KLINES_URL}?{query}",
            headers={"User-Agent": "btc-signal-lab-public-data/0.1"},
        )
        with urlopen(request, timeout=timeout) as response:
            batch = json.loads(response.read().decode("utf-8"))
        if not isinstance(batch, list):
            raise ValueError(f"unexpected Binance response: {batch!r}")
        if not batch:
            break
        raw_rows.extend(batch)
        last_open = int(batch[-1][0])
        next_cursor = last_open + step
        if next_cursor <= cursor:
            raise ValueError("Binance pagination did not advance")
        cursor = next_cursor
        if len(batch) < 1000:
            break
        time.sleep(0.05)

    rows = normalize_klines(raw_rows, start_ms, end_ms, interval)
    if not rows:
        raise ValueError("no candles returned for the requested range")
    if rows[0]["timestamp_ms"] != start_ms:
        raise ValueError("dataset does not begin at the requested candle boundary")
    if rows[-1]["timestamp_ms"] != end_ms - step:
        raise ValueError("dataset does not reach the final requested candle boundary")
    expected_count = (end_ms - start_ms) // step
    if len(rows) != expected_count:
        raise ValueError(f"expected {expected_count} candles but received {len(rows)}")
    return rows


def save_dataset(rows: Sequence[dict[str, Any]], csv_path: str | Path, *,
                 symbol: str, interval: str, start: str, end: str,
                 source_url: str = BINANCE_KLINES_URL) -> dict[str, Any]:
    """Write normalized CSV plus a JSON manifest containing source and SHA-256."""
    if not rows:
        raise ValueError("refusing to save an empty dataset")
    destination = Path(csv_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row[field] for field in CSV_FIELDS})
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    manifest = {
        "dataset_schema_version": "1.0",
        "source": source_url,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "symbol": symbol.upper(),
        "interval": interval,
        "start_utc": parse_utc(start).isoformat().replace("+00:00", "Z"),
        "end_utc_exclusive": parse_utc(end).isoformat().replace("+00:00", "Z"),
        "timestamp_semantics": "UTC candle open time; end is exclusive",
        "row_count": len(rows),
        "csv_sha256": digest,
        "validation": "finite OHLCV, unique ordered timestamps, contiguous candles",
    }
    manifest_path = destination.with_suffix(destination.suffix + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest
