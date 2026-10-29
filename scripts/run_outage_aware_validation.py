#!/usr/bin/env python3
"""Narrow outage-aware validation of BTCUSDT Spot 1h candles for 2023.

This is separate from the canonical strict downloader. It verifies each official
Binance Vision monthly archive against its published SHA-256, preserves gaps,
and permits only the pre-registered 2023-03-24 13:00-14:00 UTC gap.
"""
from __future__ import annotations
import csv, hashlib, io, json, math, os, re, zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from btc_signal_lab.segmented_evaluation import evaluate_contiguous_segments

SYMBOL, INTERVAL, STEP = "BTCUSDT", "1h", 3_600_000
START, END = "2023-01-01T00:00:00Z", "2024-01-01T00:00:00Z"
EXPECTED_GAP = {"gap_start_utc":"2023-03-24T13:00:00Z","gap_end_utc":"2023-03-24T14:00:00Z","status":"excluded_documented_outage","event_id":"binance-spot-halt-2023-03-24"}
BASE = "https://data.binance.vision/data/spot/monthly/klines"
ROOT = Path(__file__).resolve().parents[1]
EVENT_PATH = ROOT / "docs/research/binance-spot-outage-2023-03-24.json"
OUT = Path(os.environ.get("OUTPUT_DIR", "validation-artifacts"))

def fetch(url):
    with urlopen(Request(url, headers={"User-Agent":"btc-signal-lab-outage-aware-research/1.0"}), timeout=60) as r:
        return r.read()

def months(start, end):
    y, m = start.year, start.month
    while (y, m) < (end.year, end.month):
        yield y, m
        if m == 12: y, m = y + 1, 1
        else: m += 1

def parse_archive(blob, url, start_ms, end_ms):
    rows = []
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if len(names) != 1: raise ValueError(f"unexpected archive contents: {url}")
        with z.open(names[0]) as raw:
            for line, row in enumerate(csv.reader(io.TextIOWrapper(raw, encoding="utf-8")), 1):
                if not row or not row[0].strip().lstrip("-").isdigit(): continue
                if len(row) < 6: raise ValueError(f"malformed row {line}: {url}")
                ts = int(row[0])
                if not start_ms <= ts < end_ms: continue
                try: o, h, l, c, v = map(float, row[1:6])
                except (TypeError, ValueError) as e: raise ValueError(f"invalid OHLCV row {line}: {url}") from e
                if any(not math.isfinite(x) for x in (o,h,l,c,v)) or min(o,h,l,c) <= 0 or v < 0 or h < l or not l <= o <= h or not l <= c <= h:
                    raise ValueError(f"invalid OHLCV values at row {line}: {url}")
                rows.append({"timestamp_ms":ts,"timestamp":datetime.fromtimestamp(ts/1000,timezone.utc).isoformat().replace("+00:00","Z"),"open":o,"high":h,"low":l,"close":c,"volume":v})
    return rows

def main():
    start = datetime.fromisoformat(START.replace("Z","+00:00")); end = datetime.fromisoformat(END.replace("Z","+00:00"))
    start_ms, end_ms = int(start.timestamp()*1000), int(end.timestamp()*1000)
    event_bytes = EVENT_PATH.read_bytes(); event = json.loads(event_bytes.decode("utf-8"))
    archives, candles, previous = [], [], None
    for year, month in months(start, end):
        name = f"{SYMBOL}-{INTERVAL}-{year}-{month:02d}.zip"
        url = f"{BASE}/{SYMBOL}/{INTERVAL}/{name}"
        blob = fetch(url); checksum_url = url + ".CHECKSUM"
        checksum_text = fetch(checksum_url).decode("utf-8")
        m = re.search(r"\b([0-9a-fA-F]{64})\b", checksum_text)
        if not m: raise ValueError(f"cannot parse published checksum: {checksum_url}")
        actual, published = hashlib.sha256(blob).hexdigest(), m.group(1).lower()
        if actual != published: raise ValueError(f"published checksum mismatch: {url}")
        month_rows = parse_archive(blob, url, start_ms, end_ms)
        for row in month_rows:
            ts = row["timestamp_ms"]
            if previous is not None and ts <= previous: raise ValueError("duplicate/out-of-order timestamps across monthly archives")
            candles.append(row); previous = ts
        archives.append({"url":url,"sha256":actual,"published_checksum_url":checksum_url,"published_sha256":published,"row_count_in_requested_range":len(month_rows)})
    expected = (end_ms-start_ms)//STEP
    if not candles or candles[0]["timestamp_ms"] != start_ms or candles[-1]["timestamp_ms"] != end_ms-STEP:
        raise ValueError("source data do not reach both registered range boundaries")
    if len(candles) != expected-1:
        raise ValueError(f"expected exactly one missing hourly candle ({expected-1} rows), got {len(candles)}")
    result = evaluate_contiguous_segments(candles, interval_ms=STEP, venue="Binance", market="Spot", symbol=SYMBOL, outage_events=[event], initial_capital=10000.0, fee_rate=0.001, slippage_bps=5.0, horizon_bars=24)
    gaps = result["outage_policy"]["excluded_gaps"]
    if gaps != [EXPECTED_GAP]: raise ValueError(f"observed gap differs from pre-registered gap: {gaps!r}")
    if result["outage_policy"]["matched_event_ids"] != [EXPECTED_GAP["event_id"]]: raise ValueError("outage event provenance mismatch")
    if result["segment_count"] != 2 or result["total_candles"] != len(candles): raise ValueError("unexpected segment/candle accounting")
    OUT.mkdir(parents=True, exist_ok=True)
    csv_path = OUT / "BTCUSDT_recovery_1h_outage_aware.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["timestamp","timestamp_ms","open","high","low","close","volume"]); w.writeheader(); w.writerows(candles)
    report = {
        "report_schema_version":"1.0","protocol":"explicit-outage-aware-segmented-validation","data_partition":"validation","untouched_final_test":False,
        "window":"recovery","symbol":SYMBOL,"market":"Spot","interval":INTERVAL,"start_utc":START,"end_utc_exclusive":END,
        "code_commit":os.environ.get("GITHUB_SHA","local-unpinned"),
        "parameters":{"initial_capital":10000.0,"fee_rate_per_side":0.001,"slippage_bps_per_side":5.0,"forward_horizon_bars":24},
        "data_provenance":{"source":"official Binance Vision monthly Spot klines archives","archives":archives,"observed_row_count":len(candles),"expected_contiguous_row_count":expected,"missing_candle_count":expected-len(candles),"csv_sha256":hashlib.sha256(csv_path.read_bytes()).hexdigest(),"event_evidence_path":"docs/research/binance-spot-outage-2023-03-24.json","event_evidence_sha256":hashlib.sha256(event_bytes).hexdigest(),"event_evidence":event},
        "segmented_evaluation":result,
        "interpretation_guardrails":["Opt-in research result; not the canonical strict validation result.","No missing candle was synthesized, interpolated, forward-filled, or replaced with another venue.","Only the exact pre-registered 2023-03-24 13:00-14:00 UTC gap is permitted.","Each segment has independent initial capital; do not compound segment returns into one continuous equity curve.","The reserved 2025-02-01 through 2026-02-01 final-test interval was not accessed.","This report does not establish a trading edge or guarantee future performance."]
    }
    report_path = OUT / "BTCUSDT_recovery_1h_outage_aware.report.json"
    report_path.write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"report_path":str(report_path),"csv_path":str(csv_path),"observed_candles":len(candles),"segment_count":result["segment_count"],"excluded_gaps":gaps,"matched_event_ids":result["outage_policy"]["matched_event_ids"],"segments":[{"segment_index":s["segment_index"],"start_timestamp_ms":s["start_timestamp_ms"],"end_timestamp_ms":s["end_timestamp_ms"],"candle_count":s["candle_count"],"backtest":{k:s["backtest"][k] for k in ("net_return_pct","max_drawdown_pct","trade_count")} if s["backtest"] else None,"buy_and_hold":{k:s["benchmark"][k] for k in ("net_return_pct","max_drawdown_pct")} if s["benchmark"] else None,"comparison":s["comparison"],"forward_horizon":{k:s["forward_horizon"][k] for k in ("observation_count","directional_accuracy_pct")} if s["forward_horizon"] else None} for s in result["segments"]]},indent=2,sort_keys=True,allow_nan=False))

if __name__ == "__main__": main()
