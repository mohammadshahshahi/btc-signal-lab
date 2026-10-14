"""Public, credential-free Binance OHLCV download and dataset provenance helpers.

This module is opt-in and separate from signal generation/backtesting. It never
uses API keys and only downloads public spot candles.
"""
from __future__ import annotations

import csv
import hashlib
import io
import zipfile
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlencode
from urllib.request import Request, urlopen

INTERVAL_MS = {"1m": 60_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}
BINANCE_KLINES_URL = "https://data-api.binance.vision/api/v3/klines"
BINANCE_KLINES_FALLBACK_URL = "https://api.binance.com/api/v3/klines"
BINANCE_ARCHIVE_SOURCE = "https://data.binance.vision/data/spot/monthly/klines"
KUCOIN_KLINES_URL = "https://api.kucoin.com/api/v1/market/candles"
BINANCE_KLINES_SOURCES = (BINANCE_KLINES_URL, BINANCE_KLINES_FALLBACK_URL, BINANCE_ARCHIVE_SOURCE, KUCOIN_KLINES_URL)
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
    previous_opened: int | None = None
    for index, raw in enumerate(payload):
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or len(raw) < 6:
            raise ValueError(f"kline[{index}] must contain at least six fields")
        try:
            opened = int(raw[0])
            values = [float(raw[i]) for i in (1, 2, 3, 4, 5)]
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"kline[{index}] contains invalid numeric data") from exc
        # Validate source order before range filtering or normalization. Sorting here
        # would hide broken pagination / out-of-order payloads from the caller.
        if previous_opened is not None and opened <= previous_opened:
            problem = "duplicate" if opened == previous_opened else "out-of-order"
            raise ValueError(
                f"kline payload is {problem} at index {index}: "
                f"timestamp {opened} follows {previous_opened}"
            )
        previous_opened = opened
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
    timestamps = [row["timestamp_ms"] for row in rows]
    for previous, current in zip(timestamps, timestamps[1:]):
        if current - previous != step:
            raise ValueError(f"dataset has a candle gap between {previous} and {current}")
    return rows


def _download_from_source(symbol: str, interval: str, start_ms: int, end_ms: int,
                          source_url: str, timeout: float) -> list[dict[str, Any]]:
    """Fetch and fully validate one source; never patch or interpolate missing candles."""
    step = INTERVAL_MS[interval]
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
            f"{source_url}?{query}",
            headers={"User-Agent": "btc-signal-lab-public-data/0.2"},
        )
        with urlopen(request, timeout=timeout) as response:
            batch = json.loads(response.read().decode("utf-8"))
        if not isinstance(batch, list):
            raise ValueError(f"unexpected Binance response from {source_url}: {batch!r}")
        if not batch:
            break
        raw_rows.extend(batch)
        last_open = int(batch[-1][0])
        next_cursor = last_open + step
        if next_cursor <= cursor:
            raise ValueError(f"Binance pagination did not advance for {source_url}")
        cursor = next_cursor
        if cursor < end_ms:
            time.sleep(0.05)

    rows = normalize_klines(raw_rows, start_ms, end_ms, interval)
    if not rows:
        raise ValueError(f"no candles returned from {source_url}")
    if rows[0]["timestamp_ms"] != start_ms:
        raise ValueError(f"dataset from {source_url} does not begin at requested candle boundary")
    if rows[-1]["timestamp_ms"] != end_ms - step:
        raise ValueError(f"dataset from {source_url} does not reach final requested candle boundary")
    expected_count = (end_ms - start_ms) // step
    if len(rows) != expected_count:
        raise ValueError(f"expected {expected_count} candles but received {len(rows)} from {source_url}")
    return rows


def _download_from_kucoin(symbol: str, interval: str, start_ms: int, end_ms: int,
                          timeout: float) -> list[dict[str, Any]]:
    """Download one contiguous window from KuCoin public spot candles as a fallback."""
    interval_type = {"1h": "1hour", "4h": "4hour", "1d": "1day"}[interval]
    step = INTERVAL_MS[interval]
    cursor = start_ms
    raw_rows: list[list[Any]] = []
    while cursor < end_ms:
        chunk_end = min(cursor + step * 1000, end_ms)
        query = urlencode({
            "symbol": "BTC-USDT" if symbol.strip().upper() == "BTCUSDT" else symbol.strip().upper(),
            "type": interval_type,
            "startAt": cursor // 1000,
            "endAt": (chunk_end - step) // 1000,
        })
        request = Request(
            f"{KUCOIN_KLINES_URL}?{query}",
            headers={"User-Agent": "btc-signal-lab-public-data/0.2"},
        )
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict) or payload.get("code") != "200000" or not isinstance(payload.get("data"), list):
            raise ValueError(f"unexpected KuCoin response: {payload!r}")
        batch = payload["data"]
        # KuCoin's candle endpoint returns rows newest-first. Normalize this
        # provider-specific response order explicitly before applying the shared
        # strict ascending-order validator; do not sort arbitrary input payloads.
        # Row shape: [time seconds, open, close, high, low, volume, turnover].
        for item in reversed(batch):
            if not isinstance(item, list) or len(item) < 6:
                raise ValueError("KuCoin candle row has an invalid shape")
            raw_rows.append([
                int(item[0]) * 1000, item[1], item[3], item[4], item[2], item[5]
            ])
        cursor = chunk_end
        if cursor < end_ms:
            time.sleep(0.05)

    rows = normalize_klines(raw_rows, start_ms, end_ms, interval)
    expected_count = (end_ms - start_ms) // step
    if not rows or rows[0]["timestamp_ms"] != start_ms:
        raise ValueError("KuCoin dataset does not begin at requested candle boundary")
    if rows[-1]["timestamp_ms"] != end_ms - step or len(rows) != expected_count:
        raise ValueError(f"KuCoin dataset is incomplete: expected {expected_count} candles, received {len(rows)}")
    return rows


def _download_from_binance_archive(symbol: str, interval: str, start_ms: int,
                                   end_ms: int, timeout: float) -> list[dict[str, Any]]:
    """Download monthly Binance Vision ZIP archives and validate full coverage."""
    start_dt = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc)
    end_dt = datetime.fromtimestamp((end_ms - 1) / 1000, tz=timezone.utc)
    month = datetime(start_dt.year, start_dt.month, 1, tzinfo=timezone.utc)
    final_month = datetime(end_dt.year, end_dt.month, 1, tzinfo=timezone.utc)
    raw_rows: list[list[Any]] = []
    while month <= final_month:
        archive_name = f"{symbol.upper()}-{interval}-{month.year}-{month.month:02d}.zip"
        url = f"{BINANCE_ARCHIVE_SOURCE}/{symbol.upper()}/{interval}/{archive_name}"
        request = Request(url, headers={"User-Agent": "btc-signal-lab-public-data/0.2"})
        with urlopen(request, timeout=timeout) as response:
            archive_bytes = response.read()
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
            if len(csv_names) != 1:
                raise ValueError(f"unexpected archive contents from {url}")
            with archive.open(csv_names[0]) as handle:
                for row in csv.reader(io.TextIOWrapper(handle, encoding="utf-8")):
                    if not row or not row[0].strip().lstrip("-").isdigit():
                        continue
                    raw_rows.append(row[:6])
        if month.month == 12:
            month = datetime(month.year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            month = datetime(month.year, month.month + 1, 1, tzinfo=timezone.utc)

    rows = normalize_klines(raw_rows, start_ms, end_ms, interval)
    step = INTERVAL_MS[interval]
    expected_count = (end_ms - start_ms) // step
    if not rows or rows[0]["timestamp_ms"] != start_ms:
        raise ValueError("Binance Vision archive does not begin at requested candle boundary")
    if rows[-1]["timestamp_ms"] != end_ms - step or len(rows) != expected_count:
        raise ValueError(
            f"Binance Vision archive is incomplete: expected {expected_count} candles, received {len(rows)}"
        )
    return rows


def download_binance_klines_with_source(
    symbol: str, interval: str, start: str, end: str, *, timeout: float = 30.0,
    sources: Sequence[str] = BINANCE_KLINES_SOURCES,
) -> tuple[list[dict[str, Any]], str]:
    """Download verified candles, trying a second public Binance endpoint if needed.

    Each source is independently validated for completeness and continuity. No
    candles are fabricated, interpolated, or silently removed. The URL that
    supplied the accepted dataset is returned for provenance manifests.
    """
    if not isinstance(symbol, str) or not symbol.strip() or not symbol.isalnum():
        raise ValueError("symbol must be an alphanumeric spot symbol such as BTCUSDT")
    if interval not in INTERVAL_MS:
        raise ValueError(f"supported intervals: {', '.join(INTERVAL_MS)}")
    if not sources:
        raise ValueError("at least one public Binance data source is required")
    start_dt, end_dt = parse_utc(start), parse_utc(end)
    start_ms, end_ms = int(start_dt.timestamp() * 1000), int(end_dt.timestamp() * 1000)
    step = INTERVAL_MS[interval]
    if end_ms <= start_ms:
        raise ValueError("end must be later than start")
    if start_ms % step or end_ms % step:
        raise ValueError(f"start and end must align to {interval} candle boundaries")

    failures: list[str] = []
    # Retry the same provider before switching venues: intermittent truncated
    # responses must not immediately force a cross-exchange fallback. Every
    # attempt is independently validated and no missing candle is synthesized.
    attempts_per_source = 2
    for source_url in sources:
        for attempt in range(1, attempts_per_source + 1):
            try:
                if source_url == KUCOIN_KLINES_URL:
                    if symbol.strip().upper() not in {"BTCUSDT", "BTC-USDT"}:
                        raise ValueError("KuCoin fallback currently supports BTCUSDT only")
                    rows = _download_from_kucoin(symbol, interval, start_ms, end_ms, timeout)
                elif source_url == BINANCE_ARCHIVE_SOURCE:
                    rows = _download_from_binance_archive(symbol, interval, start_ms, end_ms, timeout)
                else:
                    rows = _download_from_source(symbol, interval, start_ms, end_ms, source_url, timeout)
                return rows, source_url
            except Exception as exc:
                failures.append(
                    f"{source_url} (attempt {attempt}/{attempts_per_source}): "
                    f"{type(exc).__name__}: {exc}"
                )
                if attempt < attempts_per_source:
                    time.sleep(0.25)
    raise ValueError("all public market-data sources failed strict dataset validation: " + " | ".join(failures))



def aggregate_minute_klines(
    payload: Sequence[Sequence[Any]], start_ms: int, end_ms: int, target_interval: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Aggregate complete, strictly ordered Binance 1m rows into UTC target bars.

    The requested range is [start_ms, end_ms). Every target bucket must contain
    exactly 60, 240, or 1,440 consecutive minute candles. No gaps are filled.
    """
    if target_interval not in {"1h", "4h", "1d"}:
        raise ValueError("target_interval must be 1h, 4h, or 1d")
    target_step = INTERVAL_MS[target_interval]
    minute_step = INTERVAL_MS["1m"]
    if end_ms <= start_ms or start_ms % target_step or end_ms % target_step:
        raise ValueError("start and end must align to complete UTC target-interval boundaries")

    expected_minutes = (end_ms - start_ms) // minute_step
    minute_rows = normalize_klines(payload, start_ms, end_ms, "1m")
    if len(minute_rows) != expected_minutes:
        raise ValueError(
            f"incomplete 1m source range: expected {expected_minutes} minute candles, "
            f"received {len(minute_rows)}"
        )
    if not minute_rows or minute_rows[0]["timestamp_ms"] != start_ms:
        raise ValueError("1m source does not begin at the requested UTC boundary")
    if minute_rows[-1]["timestamp_ms"] != end_ms - minute_step:
        raise ValueError("1m source does not reach the final requested minute")

    constituents_per_bucket = target_step // minute_step
    if expected_minutes % constituents_per_bucket:
        raise ValueError("1m source does not contain an integer number of complete target buckets")

    aggregated: list[dict[str, Any]] = []
    actual_counts: list[int] = []
    for offset in range(0, expected_minutes, constituents_per_bucket):
        bucket = minute_rows[offset:offset + constituents_per_bucket]
        bucket_start = start_ms + offset * minute_step
        if len(bucket) != constituents_per_bucket:
            raise ValueError("incomplete final target bucket")
        expected_timestamps = [
            bucket_start + index * minute_step for index in range(constituents_per_bucket)
        ]
        if [row["timestamp_ms"] for row in bucket] != expected_timestamps:
            raise ValueError(f"target bucket at {bucket_start} has missing or misaligned 1m constituents")
        aggregated.append({
            "timestamp_ms": bucket_start,
            "timestamp": datetime.fromtimestamp(
                bucket_start / 1000, timezone.utc
            ).isoformat().replace("+00:00", "Z"),
            "open": bucket[0]["open"],
            "high": max(row["high"] for row in bucket),
            "low": min(row["low"] for row in bucket),
            "close": bucket[-1]["close"],
            "volume": sum(row["volume"] for row in bucket),
        })
        actual_counts.append(len(bucket))

    provenance = {
        "source_interval": "1m",
        "target_interval": target_interval,
        "aggregation_formula": {
            "open": "first constituent open",
            "high": "maximum constituent high",
            "low": "minimum constituent low",
            "close": "last constituent close",
            "volume": "sum of constituent volumes",
        },
        "expected_constituents_per_bucket": constituents_per_bucket,
        "actual_constituent_counts": {
            "bucket_count": len(actual_counts),
            "minimum": min(actual_counts),
            "maximum": max(actual_counts),
            "total": sum(actual_counts),
        },
    }
    return aggregated, provenance


def download_binance_1m_archive_aggregate(
    symbol: str, target_interval: str, start: str, end: str, *, timeout: float = 30.0
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Download same-venue Binance Spot 1m monthly archives and aggregate strictly."""
    if not isinstance(symbol, str) or not symbol.strip() or not symbol.isalnum():
        raise ValueError("symbol must be an alphanumeric spot symbol such as BTCUSDT")
    if target_interval not in {"1h", "4h", "1d"}:
        raise ValueError("target_interval must be 1h, 4h, or 1d")
    start_dt, end_dt = parse_utc(start), parse_utc(end)
    start_ms, end_ms = int(start_dt.timestamp() * 1000), int(end_dt.timestamp() * 1000)
    target_step = INTERVAL_MS[target_interval]
    if end_ms <= start_ms or start_ms % target_step or end_ms % target_step:
        raise ValueError("start and end must align to complete UTC target-interval boundaries")

    month = datetime(start_dt.year, start_dt.month, 1, tzinfo=timezone.utc)
    final_month = datetime(
        datetime.fromtimestamp((end_ms - 1) / 1000, timezone.utc).year,
        datetime.fromtimestamp((end_ms - 1) / 1000, timezone.utc).month,
        1, tzinfo=timezone.utc,
    )
    raw_minutes: list[list[Any]] = []
    archive_urls: list[str] = []
    archive_hashes: list[dict[str, str]] = []
    while month <= final_month:
        archive_name = f"{symbol.upper()}-1m-{month.year}-{month.month:02d}.zip"
        url = f"{BINANCE_ARCHIVE_SOURCE}/{symbol.upper()}/1m/{archive_name}"
        request = Request(url, headers={"User-Agent": "btc-signal-lab-public-data/0.3"})
        with urlopen(request, timeout=timeout) as response:
            archive_bytes = response.read()
        archive_urls.append(url)
        archive_hashes.append({
            "url": url,
            "sha256": hashlib.sha256(archive_bytes).hexdigest(),
        })
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
            if len(csv_names) != 1:
                raise ValueError(f"unexpected 1m archive contents from {url}")
            with archive.open(csv_names[0]) as handle:
                for row in csv.reader(io.TextIOWrapper(handle, encoding="utf-8")):
                    if not row or not row[0].strip().lstrip("-").isdigit():
                        continue
                    raw_minutes.append(row[:6])
        if month.month == 12:
            month = datetime(month.year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            month = datetime(month.year, month.month + 1, 1, tzinfo=timezone.utc)

    aggregated, provenance = aggregate_minute_klines(
        raw_minutes, start_ms, end_ms, target_interval
    )
    provenance.update({
        "source": "Binance Spot monthly 1m archives",
        "source_archive_urls": archive_urls,
        "source_archive_sha256": archive_hashes,
        "start_utc": start_dt.isoformat().replace("+00:00", "Z"),
        "end_utc_exclusive": end_dt.isoformat().replace("+00:00", "Z"),
    })
    return aggregated, provenance


def download_binance_klines(symbol: str, interval: str, start: str, end: str,
                            *, timeout: float = 30.0) -> list[dict[str, Any]]:
    """Backward-compatible helper returning verified rows from either public source."""
    rows, _source_url = download_binance_klines_with_source(
        symbol, interval, start, end, timeout=timeout
    )
    return rows


def save_dataset(rows: Sequence[dict[str, Any]], csv_path: str | Path, *,
                 symbol: str, interval: str, start: str, end: str,
                 source_url: str = BINANCE_KLINES_URL,
                 aggregation_provenance: dict[str, Any] | None = None) -> dict[str, Any]:
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
    if aggregation_provenance is not None:
        manifest["aggregation"] = aggregation_provenance
    manifest_path = destination.with_suffix(destination.suffix + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest
