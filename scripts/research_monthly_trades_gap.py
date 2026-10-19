#!/usr/bin/env python3
"""Stream-scan Binance's official monthly BTCUSDT Spot trades ZIP for the 2023-03-24 gap.

The archive is large, so download to disk in chunks and never keep the ZIP in RAM. This scan is intentionally isolated from canonical data.
The scan is evidence-only and does not modify canonical candles.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

URL = "https://data.binance.vision/data/spot/monthly/trades/BTCUSDT/BTCUSDT-trades-2023-03.zip"
CHECKSUM_URL = URL + ".CHECKSUM"
START = int(datetime(2023, 3, 24, 12, 40, tzinfo=timezone.utc).timestamp() * 1000)
END = int(datetime(2023, 3, 24, 14, 0, tzinfo=timezone.utc).timestamp() * 1000)
OUT = Path("aggtrades-gap-artifacts")
ZIP_PATH = Path("/tmp/BTCUSDT-trades-2023-03.zip")


def iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat().replace("+00:00", "Z")


def stream_download(url: str, path: Path) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "btc-signal-lab-gap-research/1.0"})
    digest = hashlib.sha256()
    size = 0
    with urllib.request.urlopen(req, timeout=120) as response:
        status = response.status
        headers = dict(response.headers.items())
        with path.open("wb") as target:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                target.write(chunk)
                digest.update(chunk)
                size += len(chunk)
    return {
        "url": url, "http_status": status, "downloaded_bytes": size,
        "content_length_header": headers.get("Content-Length"),
        "last_modified": headers.get("Last-Modified"), "etag": headers.get("ETag"),
        "sha256": digest.hexdigest(),
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    meta = stream_download(URL, ZIP_PATH)
    checksum_req = urllib.request.Request(CHECKSUM_URL, headers={"User-Agent": "btc-signal-lab-gap-research/1.0"})
    with urllib.request.urlopen(checksum_req, timeout=30) as response:
        checksum_text = response.read().decode("utf-8", errors="replace").strip()
    expected_hash = checksum_text.split()[0] if checksum_text else None
    meta["checksum_url"] = CHECKSUM_URL
    meta["published_checksum_text"] = checksum_text
    meta["published_checksum_matches_download"] = expected_hash == meta["sha256"]

    rows = 0
    target_rows = 0
    id_discontinuities = 0
    timestamp_regressions = 0
    previous_id = previous_ts = None
    last_before = first_after = None
    first_target = last_target = None
    with zipfile.ZipFile(ZIP_PATH) as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
        if len(names) != 1:
            raise ValueError(f"Expected one CSV in archive, got {names!r}")
        with zf.open(names[0]) as raw:
            stream = io.TextIOWrapper(raw, encoding="utf-8", newline="")
            for line, row in enumerate(csv.reader(stream), 1):
                if len(row) < 6:
                    raise ValueError(f"Row {line} has {len(row)} columns; expected >=6")
                trade_id, ts = int(row[0]), int(row[4])
                if previous_id is not None and trade_id != previous_id + 1:
                    id_discontinuities += 1
                if previous_ts is not None and ts < previous_ts:
                    timestamp_regressions += 1
                if ts < START:
                    last_before = {"trade_id": trade_id, "timestamp_ms": ts, "timestamp_utc": iso(ts)}
                elif ts < END:
                    target_rows += 1
                    if first_target is None:
                        first_target = {"trade_id": trade_id, "timestamp_ms": ts, "timestamp_utc": iso(ts)}
                    last_target = {"trade_id": trade_id, "timestamp_ms": ts, "timestamp_utc": iso(ts)}
                elif first_after is None:
                    first_after = {"trade_id": trade_id, "timestamp_ms": ts, "timestamp_utc": iso(ts)}
                previous_id, previous_ts = trade_id, ts
                rows += 1

    report = {
        "schema_version": "1.0",
        "purpose": "independent monthly raw-trades archive scan for missing-minute source coverage",
        "archive": meta,
        "csv_rows_scanned": rows,
        "trade_id_discontinuity_count": id_discontinuities,
        "timestamp_regression_count": timestamp_regressions,
        "target_interval_start_utc": iso(START),
        "target_interval_end_exclusive_utc": iso(END),
        "target_trade_rows": target_rows,
        "first_target_trade": first_target,
        "last_target_trade": last_target,
        "last_trade_before_target": last_before,
        "first_trade_at_or_after_target_end": first_after,
        "strict_primary_kline_gate_passed": False,
        "verdict": "MONTHLY_RAW_TRADES_CONTAIN_TARGET_TRADES" if target_rows else "MONTHLY_RAW_TRADES_ALSO_MISSING_TARGET_INTERVAL",
        "guardrails": ["streamed to disk", "never modifies canonical klines", "no synthetic bars", "no cross-venue substitution", "does not clear strict historical gate"],
    }
    path = OUT / "monthly-raw-trades-gap-report.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    ZIP_PATH.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
