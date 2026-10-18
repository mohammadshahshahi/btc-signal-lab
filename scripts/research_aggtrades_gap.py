#!/usr/bin/env python3
"""Produce isolated Binance Spot aggTrades evidence for the known 2023 kline gap.

This tool never patches the primary kline dataset. Output bars are explicitly
labelled reconstructed/sensitivity data and cannot clear the strict source gate.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
import time
import urllib.request
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

BASE = "https://data.binance.vision/data/spot/daily"
SYMBOL = "BTCUSDT"
DAY = "2023-03-24"
GAP_START = int(datetime(2023, 3, 24, 12, 40, tzinfo=timezone.utc).timestamp() * 1000)
GAP_END = int(datetime(2023, 3, 24, 14, 0, tzinfo=timezone.utc).timestamp() * 1000)
MINUTE_MS = 60_000
OUT = Path("aggtrades-gap-artifacts")


def fetch(url: str) -> tuple[bytes, dict]:
    request = urllib.request.Request(url, headers={"User-Agent": "btc-signal-lab-gap-research/1.0"})
    with urllib.request.urlopen(request, timeout=90) as response:
        data = response.read()
        headers = dict(response.headers.items())
    return data, {
        "url": url,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "http_status": 200,
        "content_length_header": headers.get("Content-Length"),
        "downloaded_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def zip_rows(data: bytes):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        members = [name for name in archive.namelist() if not name.endswith("/")]
        if len(members) != 1:
            raise ValueError(f"expected one CSV member in ZIP, found {members!r}")
        with archive.open(members[0]) as stream:
            text = io.TextIOWrapper(stream, encoding="utf-8", newline="")
            yield from csv.reader(text)


def d(value: str) -> Decimal:
    return Decimal(value)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    agg_url = f"{BASE}/aggTrades/{SYMBOL}/{SYMBOL}-aggTrades-{DAY}.zip"
    kline_url = f"{BASE}/klines/{SYMBOL}/1m/{SYMBOL}-1m-{DAY}.zip"
    agg_bytes, agg_meta = fetch(agg_url)
    kline_bytes, kline_meta = fetch(kline_url)

    bars = {}
    last_agg_id = None
    last_trade_time = None
    agg_rows = 0
    agg_id_breaks = []
    timestamp_regressions = []
    min_id = max_id = None
    for row_num, row in enumerate(zip_rows(agg_bytes), start=1):
        if len(row) < 8:
            raise ValueError(f"aggTrades row {row_num} has {len(row)} columns, expected 8")
        agg_id, price, qty, first_id, final_id, ts, buyer_maker, _best_match = row[:8]
        agg_id, first_id, final_id, ts = int(agg_id), int(first_id), int(final_id), int(ts)
        price_d, qty_d = d(price), d(qty)
        if price_d <= 0 or qty_d <= 0:
            raise ValueError(f"non-positive price/quantity at aggTrades row {row_num}")
        if last_agg_id is not None and agg_id != last_agg_id + 1:
            if len(agg_id_breaks) < 100:
                agg_id_breaks.append({"previous": last_agg_id, "current": agg_id})
        if last_trade_time is not None and ts < last_trade_time:
            timestamp_regressions.append({"row": row_num, "previous_ms": last_trade_time, "current_ms": ts})
        last_agg_id, last_trade_time = agg_id, ts
        min_id = agg_id if min_id is None else min(min_id, agg_id)
        max_id = agg_id if max_id is None else max(max_id, agg_id)
        agg_rows += 1
        minute = ts - (ts % MINUTE_MS)
        bar = bars.get(minute)
        is_buyer_maker = buyer_maker.strip().lower() == "true"
        if bar is None:
            bars[minute] = {
                "open": price_d, "high": price_d, "low": price_d, "close": price_d,
                "volume": qty_d, "quote_volume": price_d * qty_d,
                "aggtrade_rows": 1, "underlying_trade_count": final_id - first_id + 1,
                "taker_buy_base_volume": Decimal("0") if is_buyer_maker else qty_d,
                "taker_buy_quote_volume": Decimal("0") if is_buyer_maker else price_d * qty_d,
            }
        else:
            bar["high"] = max(bar["high"], price_d)
            bar["low"] = min(bar["low"], price_d)
            bar["close"] = price_d
            bar["volume"] += qty_d
            bar["quote_volume"] += price_d * qty_d
            bar["aggtrade_rows"] += 1
            bar["underlying_trade_count"] += final_id - first_id + 1
            if not is_buyer_maker:
                bar["taker_buy_base_volume"] += qty_d
                bar["taker_buy_quote_volume"] += price_d * qty_d

    official = {}
    for row_num, row in enumerate(zip_rows(kline_bytes), start=1):
        if len(row) < 12:
            raise ValueError(f"kline row {row_num} has {len(row)} columns, expected 12")
        ts = int(row[0])
        official[ts] = {
            "open": d(row[1]), "high": d(row[2]), "low": d(row[3]),
            "close": d(row[4]), "volume": d(row[5]),
            "quote_volume": d(row[7]), "trade_count": int(row[8]),
            "taker_buy_base_volume": d(row[9]), "taker_buy_quote_volume": d(row[10]),
        }

    expected_gap = list(range(GAP_START, GAP_END, MINUTE_MS))
    missing_reconstructed = [ts for ts in expected_gap if ts not in bars]
    adjacent = [GAP_START - MINUTE_MS, GAP_END]
    comparisons = []
    for ts in adjacent:
        if ts not in bars:
            comparisons.append({"timestamp_utc": datetime.fromtimestamp(ts / 1000, timezone.utc).isoformat(), "status": "NO_RECONSTRUCTED_TRADES"})
            continue
        if ts not in official:
            comparisons.append({"timestamp_utc": datetime.fromtimestamp(ts / 1000, timezone.utc).isoformat(), "status": "MISSING_FROM_OFFICIAL_KLINES"})
            continue
        fields = ["open", "high", "low", "close", "volume", "quote_volume", "taker_buy_base_volume", "taker_buy_quote_volume"]
        deltas = {field: str(bars[ts][field] - official[ts][field]) for field in fields}
        matches = all(bars[ts][field] == official[ts][field] for field in fields)
        trade_count_match = bars[ts]["underlying_trade_count"] == official[ts]["trade_count"]
        comparisons.append({
            "timestamp_utc": datetime.fromtimestamp(ts / 1000, timezone.utc).isoformat(),
            "status": "MATCH" if matches and trade_count_match else "MISMATCH",
            "all_ohlcv_and_quote_fields_exact": matches,
            "underlying_trade_count_match": trade_count_match,
            "reconstructed_underlying_trade_count": bars[ts]["underlying_trade_count"],
            "official_trade_count": official[ts]["trade_count"],
            "field_deltas_reconstructed_minus_official": deltas,
        })

    csv_path = OUT / "reconstructed_gap_1m_sensitivity.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "timestamp_utc", "open", "high", "low", "close", "base_volume",
            "quote_volume", "aggtrade_rows", "underlying_trade_count",
            "taker_buy_base_volume", "taker_buy_quote_volume", "source",
        ])
        writer.writeheader()
        for ts in expected_gap:
            if ts not in bars:
                continue
            bar = bars[ts]
            writer.writerow({
                "timestamp_utc": datetime.fromtimestamp(ts / 1000, timezone.utc).isoformat().replace("+00:00", "Z"),
                "open": str(bar["open"]), "high": str(bar["high"]), "low": str(bar["low"]),
                "close": str(bar["close"]), "base_volume": str(bar["volume"]),
                "quote_volume": str(bar["quote_volume"]), "aggtrade_rows": bar["aggtrade_rows"],
                "underlying_trade_count": bar["underlying_trade_count"],
                "taker_buy_base_volume": str(bar["taker_buy_base_volume"]),
                "taker_buy_quote_volume": str(bar["taker_buy_quote_volume"]),
                "source": "reconstructed_from_binance_spot_aggTrades_NOT_primary_klines",
            })

    report = {
        "schema_version": "1.0",
        "purpose": "isolated source-evidence/sensitivity investigation; not primary dataset repair",
        "symbol": SYMBOL,
        "day_utc": DAY,
        "gap_start_utc_inclusive": datetime.fromtimestamp(GAP_START / 1000, timezone.utc).isoformat().replace("+00:00", "Z"),
        "gap_end_utc_exclusive": datetime.fromtimestamp(GAP_END / 1000, timezone.utc).isoformat().replace("+00:00", "Z"),
        "expected_gap_minutes": len(expected_gap),
        "aggtrades_archive": agg_meta,
        "official_kline_archive": kline_meta,
        "aggtrades_rows": agg_rows,
        "aggtrade_id_min": min_id,
        "aggtrade_id_max": max_id,
        "aggtrade_id_break_count_sampled": len(agg_id_breaks),
        "aggtrade_id_break_examples": agg_id_breaks[:20],
        "timestamp_regression_count": len(timestamp_regressions),
        "timestamp_regression_examples": timestamp_regressions[:20],
        "reconstructed_minutes_in_gap": len(expected_gap) - len(missing_reconstructed),
        "minutes_without_aggtrades_in_gap": [datetime.fromtimestamp(ts / 1000, timezone.utc).isoformat().replace("+00:00", "Z") for ts in missing_reconstructed],
        "adjacent_official_kline_comparisons": comparisons,
        "reconstructed_csv_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        "reconstructed_csv_path": csv_path.name,
        "strict_primary_kline_gate_passed": False,
        "sensitivity_candidate": (
            not missing_reconstructed
            and not agg_id_breaks
            and not timestamp_regressions
            and all(item.get("status") == "MATCH" for item in comparisons)
        ),
        "limitations": [
            "aggTrades are not canonical klines; reconstruction is segregated as sensitivity data.",
            "The primary Binance kline archive remains incomplete and the strict gate remains failed.",
            "No empty-minute candles are fabricated; minutes with no aggTrades are listed as missing.",
            "Underlying trade count is estimated from inclusive first/last trade IDs per aggregate row and must be interpreted with the source schema.",
            "No cross-exchange data, interpolation, or strategy tuning is used.",
        ],
    }
    report_path = OUT / "report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
