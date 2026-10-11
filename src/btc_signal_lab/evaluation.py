"""Reproducible dataset-to-backtest evaluation pipeline."""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .backtest import run_backtest
from .market_data import INTERVAL_MS, parse_utc


def load_verified_dataset(csv_path: str | Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load CSV only if its adjacent manifest and SHA-256 agree."""
    path = Path(csv_path)
    manifest_path = path.with_suffix(path.suffix + ".manifest.json")
    if not path.is_file() or not manifest_path.is_file():
        raise FileNotFoundError("CSV and adjacent .manifest.json are both required")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != manifest.get("csv_sha256"):
        raise ValueError("CSV SHA-256 does not match dataset manifest")
    interval = manifest.get("interval")
    if interval not in INTERVAL_MS:
        raise ValueError("manifest has unsupported interval")
    start = parse_utc(manifest["start_utc"])
    end = parse_utc(manifest["end_utc_exclusive"])
    if end <= start:
        raise ValueError("manifest end must be later than start")
    rows: list[dict[str, Any]] = []
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"timestamp", "open", "high", "low", "close", "volume"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("CSV is missing required OHLCV columns")
        for index, raw in enumerate(reader):
            try:
                timestamp = parse_utc(raw["timestamp"])
                candle = {
                    "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
                    "timestamp_ms": int(timestamp.timestamp() * 1000),
                    "open": float(raw["open"]),
                    "high": float(raw["high"]),
                    "low": float(raw["low"]),
                    "close": float(raw["close"]),
                    "volume": float(raw["volume"]),
                }
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError(f"invalid CSV row {index + 2}") from exc
            rows.append(candle)
    if len(rows) != manifest.get("row_count"):
        raise ValueError("CSV row count does not match manifest")
    step = INTERVAL_MS[interval]
    expected_count = int((end.timestamp() - start.timestamp()) * 1000 // step)
    if len(rows) != expected_count:
        raise ValueError(f"expected {expected_count} rows from manifest range, found {len(rows)}")
    if not rows or rows[0]["timestamp_ms"] != int(start.timestamp() * 1000):
        raise ValueError("first candle does not match manifest start")
    if rows[-1]["timestamp_ms"] != int(end.timestamp() * 1000) - step:
        raise ValueError("last candle does not match manifest end")
    for previous, current in zip(rows, rows[1:]):
        if current["timestamp_ms"] - previous["timestamp_ms"] != step:
            raise ValueError("CSV contains duplicate, unordered, or missing candles")
    return rows, manifest


def evaluate_dataset(
    csv_path: str | Path,
    *,
    initial_capital: float = 10_000.0,
    fee_rate: float = 0.001,
    slippage_bps: float = 5.0,
) -> dict[str, Any]:
    """Verify provenance, run backtest, and return a provenance-linked report."""
    candles, manifest = load_verified_dataset(csv_path)
    report = run_backtest(
        candles,
        initial_capital=initial_capital,
        fee_rate=fee_rate,
        slippage_bps=slippage_bps,
    )
    return {
        "report_schema_version": "1.0",
        "dataset": {
            "symbol": manifest["symbol"],
            "interval": manifest["interval"],
            "start_utc": manifest["start_utc"],
            "end_utc_exclusive": manifest["end_utc_exclusive"],
            "row_count": manifest["row_count"],
            "csv_sha256": manifest["csv_sha256"],
            "source": manifest["source"],
            "retrieved_at_utc": manifest["retrieved_at_utc"],
        },
        "assumptions": {
            "initial_capital": initial_capital,
            "fee_rate_per_side": fee_rate,
            "slippage_bps_per_side": slippage_bps,
            "execution": "signal at close, fill at next candle open",
            "strategy": "long-only BUY-to-enter, SELL-to-exit",
        },
        "results": report,
        "evaluation_generated_at_utc": datetime.now().astimezone().isoformat(),
    }


def write_report(report: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
                    encoding="utf-8")
