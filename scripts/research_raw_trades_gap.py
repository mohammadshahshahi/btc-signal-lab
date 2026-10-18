#!/usr/bin/env python3
"""Inspect official Binance Spot individual trades for the BTCUSDT 2023-03-24 gap.

Outputs isolated sensitivity evidence only. Never edits canonical klines or clears
the strict historical source gate.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import urllib.request
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

BASE = "https://data.binance.vision/data/spot/daily"
SYMBOL = "BTCUSDT"
DAY = "2023-03-24"
START = int(datetime(2023, 3, 24, 12, 40, tzinfo=timezone.utc).timestamp() * 1000)
END = int(datetime(2023, 3, 24, 14, 0, tzinfo=timezone.utc).timestamp() * 1000)
MINUTE = 60_000
OUT = Path("aggtrades-gap-artifacts")


def fetch(url: str) -> tuple[bytes, dict]:
    req = urllib.request.Request(url, headers={"User-Agent": "btc-signal-lab-gap-research/1.0"})
    with urllib.request.urlopen(req, timeout=120) as response:
        data = response.read()
        status = response.status
        headers = dict(response.headers.items())
    return data, {"url": url, "http_status": status, "downloaded_bytes": len(data),
                  "content_length_header": headers.get("Content-Length"),
                  "sha256": hashlib.sha256(data).hexdigest(),
                  "retrieved_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}


def rows_from_zip(data: bytes):
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
        if len(names) != 1:
            raise ValueError(f"Expected one CSV in archive, got {names!r}")
        with zf.open(names[0]) as stream:
            yield from csv.reader(io.TextIOWrapper(stream, encoding="utf-8", newline=""))


def dec(x: str) -> Decimal:
    return Decimal(x)


def iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    trades_url = f"{BASE}/trades/{SYMBOL}/{SYMBOL}-trades-{DAY}.zip"
    klines_url = f"{BASE}/klines/{SYMBOL}/1m/{SYMBOL}-1m-{DAY}.zip"
    trade_bytes, trade_meta = fetch(trades_url)
    kline_bytes, kline_meta = fetch(klines_url)

    bars = {}
    count = 0
    min_id = max_id = prev_id = prev_ts = None
    id_breaks = timestamp_regressions = 0
    target_rows = 0
    nearest_before = first_after = None
    max_delta_ms = 0
    max_delta_example = None
    for line, row in enumerate(rows_from_zip(trade_bytes), 1):
        if len(row) < 7:
            raise ValueError(f"Trade row {line} has {len(row)} columns; expected >=7")
        trade_id = int(row[0])
        price, qty, quote_qty, ts = dec(row[1]), dec(row[2]), dec(row[3]), int(row[4])
        buyer_maker = row[5].strip().lower() == "true"
        if price <= 0 or qty <= 0 or quote_qty < 0:
            raise ValueError(f"Invalid price/quantity at row {line}")
        if prev_id is not None and trade_id != prev_id + 1:
            id_breaks += 1
        if prev_ts is not None:
            if ts < prev_ts:
                timestamp_regressions += 1
            delta = ts - prev_ts
            if delta > max_delta_ms:
                max_delta_ms = delta
                max_delta_example = {"previous_ms": prev_ts, "current_ms": ts,
                                     "previous_utc": iso(prev_ts), "current_utc": iso(ts),
                                     "delta_ms": delta}
        if ts < START:
            nearest_before = {"trade_id": trade_id, "timestamp_ms": ts, "timestamp_utc": iso(ts)}
        elif ts < END:
            target_rows += 1
        elif first_after is None:
            first_after = {"trade_id": trade_id, "timestamp_ms": ts, "timestamp_utc": iso(ts)}
        minute = ts - ts % MINUTE
        bar = bars.get(minute)
        taker_base = Decimal(0) if buyer_maker else qty
        taker_quote = Decimal(0) if buyer_maker else quote_qty
        if bar is None:
            bars[minute] = {"open": price, "high": price, "low": price, "close": price,
                            "base_volume": qty, "quote_volume": quote_qty, "trade_count": 1,
                            "taker_buy_base_volume": taker_base,
                            "taker_buy_quote_volume": taker_quote}
        else:
            bar["high"] = max(bar["high"], price)
            bar["low"] = min(bar["low"], price)
            bar["close"] = price
            bar["base_volume"] += qty
            bar["quote_volume"] += quote_qty
            bar["trade_count"] += 1
            bar["taker_buy_base_volume"] += taker_base
            bar["taker_buy_quote_volume"] += taker_quote
        count += 1
        min_id = trade_id if min_id is None else min(min_id, trade_id)
        max_id = trade_id if max_id is None else max(max_id, trade_id)
        prev_id, prev_ts = trade_id, ts

    official = {}
    for line, row in enumerate(rows_from_zip(kline_bytes), 1):
        if len(row) < 12:
            raise ValueError(f"Kline row {line} has {len(row)} columns; expected 12")
        ts = int(row[0])
        official[ts] = {"open": dec(row[1]), "high": dec(row[2]), "low": dec(row[3]),
                        "close": dec(row[4]), "base_volume": dec(row[5]),
                        "quote_volume": dec(row[7]), "trade_count": int(row[8]),
                        "taker_buy_base_volume": dec(row[9]),
                        "taker_buy_quote_volume": dec(row[10])}

    fields = ["open", "high", "low", "close", "base_volume", "quote_volume",
              "taker_buy_base_volume", "taker_buy_quote_volume"]
    comparisons = []
    for ts in [START - MINUTE, *range(START, END, MINUTE), END]:
        if ts not in bars:
            comparisons.append({"timestamp_utc": iso(ts), "status": "NO_RAW_TRADES"})
            continue
        if ts not in official:
            comparisons.append({"timestamp_utc": iso(ts), "status": "MISSING_OFFICIAL_KLINE"})
            continue
        exact_fields = all(bars[ts][f] == official[ts][f] for f in fields)
        exact_count = bars[ts]["trade_count"] == official[ts]["trade_count"]
        comparisons.append({"timestamp_utc": iso(ts),
                            "status": "MATCH" if exact_fields and exact_count else "MISMATCH",
                            "all_price_volume_fields_exact": exact_fields,
                            "trade_count_exact": exact_count,
                            "reconstructed_trade_count": bars[ts]["trade_count"],
                            "official_trade_count": official[ts]["trade_count"]})

    csv_path = OUT / "raw_trades_reconstructed_gap_sensitivity.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp_utc", *fields, "trade_count", "source"])
        writer.writeheader()
        for ts in range(START, END, MINUTE):
            if ts in bars:
                writer.writerow({"timestamp_utc": iso(ts), **{k: str(v) for k, v in bars[ts].items()},
                                 "source": "reconstructed_from_official_binance_spot_trades_NOT_primary_klines"})

    report = {
        "schema_version": "1.0",
        "purpose": "isolated raw-trade source investigation; sensitivity output is not primary data",
        "symbol": SYMBOL, "day_utc": DAY, "target_start_utc": iso(START), "target_end_exclusive_utc": iso(END),
        "expected_gap_minutes": (END - START) // MINUTE,
        "raw_trades_archive": trade_meta, "official_kline_archive": kline_meta,
        "raw_trade_rows": count, "trade_id_min": min_id, "trade_id_max": max_id,
        "trade_id_discontinuity_count": id_breaks, "timestamp_regression_count": timestamp_regressions,
        "max_adjacent_timestamp_gap_ms": max_delta_ms, "max_adjacent_timestamp_gap": max_delta_example,
        "last_raw_trade_before_target": nearest_before, "first_raw_trade_at_or_after_end": first_after,
        "raw_trade_rows_in_target_interval": target_rows,
        "reconstructed_target_minutes": sum(ts in bars for ts in range(START, END, MINUTE)),
        "comparison_rows": comparisons,
        "strict_primary_kline_gate_passed": False,
        "verdict": "EVIDENCE_ONLY_REQUIRES_REVIEW",
        "guardrails": ["never edits canonical kline data", "no synthetic bars", "no cross-venue substitution",
                       "no parameter tuning", "does not clear historical validation gate"]
    }
    report_path = OUT / "raw-trades-gap-report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(report_path), "csv": str(csv_path),
                      "raw_trade_rows": count, "target_rows": target_rows,
                      "reconstructed_target_minutes": report["reconstructed_target_minutes"],
                      "trade_id_discontinuity_count": id_breaks,
                      "timestamp_regression_count": timestamp_regressions,
                      "max_adjacent_timestamp_gap_ms": max_delta_ms,
                      "strict_primary_kline_gate_passed": False}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
