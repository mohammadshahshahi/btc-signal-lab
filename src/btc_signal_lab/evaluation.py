"""Reproducible dataset-to-backtest evaluation pipeline."""
from __future__ import annotations

import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .backtest import run_backtest
from .benchmark import run_buy_and_hold
from .market_data import INTERVAL_MS, parse_utc
from .horizon_evaluator import evaluate_forward_horizon


def load_verified_dataset(csv_path: str | Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
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

    rows = []
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"timestamp", "open", "high", "low", "close", "volume"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("CSV is missing required OHLCV columns")
        for index, raw in enumerate(reader):
            try:
                ts = parse_utc(raw["timestamp"])
                candle = {
                    "timestamp": ts.isoformat().replace("+00:00", "Z"),
                    "timestamp_ms": int(ts.timestamp() * 1000),
                    "open": float(raw["open"]),
                    "high": float(raw["high"]),
                    "low": float(raw["low"]),
                    "close": float(raw["close"]),
                    "volume": float(raw["volume"]),
                }
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError(f"invalid CSV row {index + 2}") from exc

            prices = (candle["open"], candle["high"], candle["low"], candle["close"])
            volume = candle["volume"]
            if not all(math.isfinite(value) for value in (*prices, volume)):
                raise ValueError(f"CSV row {index + 2} contains non-finite OHLCV data")
            if min(prices) <= 0 or volume < 0:
                raise ValueError(f"CSV row {index + 2} has non-positive prices or negative volume")
            if (
                candle["high"] < candle["low"]
                or not candle["low"] <= candle["open"] <= candle["high"]
                or not candle["low"] <= candle["close"] <= candle["high"]
            ):
                raise ValueError(f"CSV row {index + 2} has inconsistent OHLC values")
            rows.append(candle)

    step = INTERVAL_MS[interval]
    expected = int((end - start).total_seconds() * 1000 // step)
    if len(rows) != manifest.get("row_count") or len(rows) != expected:
        raise ValueError("CSV row count does not match manifest range")
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
    candles, manifest = load_verified_dataset(csv_path)
    strategy = run_backtest(
        candles,
        initial_capital=initial_capital,
        fee_rate=fee_rate,
        slippage_bps=slippage_bps,
    )
    benchmark = run_buy_and_hold(
        candles,
        initial_capital=initial_capital,
        fee_rate=fee_rate,
        slippage_bps=slippage_bps,
    )
    dataset_keys = (
        "symbol", "interval", "start_utc", "end_utc_exclusive", "row_count",
        "csv_sha256", "source", "retrieved_at_utc",
    )
    return {
        "report_schema_version": "1.1",
        "dataset": {key: manifest[key] for key in dataset_keys},
        "assumptions": {
            "initial_capital": initial_capital,
            "fee_rate_per_side": fee_rate,
            "slippage_bps_per_side": slippage_bps,
            "strategy_execution": "signal at close, fill at next candle open",
            "strategy": "long-only BUY-to-enter, SELL-to-exit",
            "benchmark": "buy at second candle open and liquidate at final candle close",
            "benchmark_comparability": (
                "same dataset, starting capital, fees, slippage, and earliest possible "
                "next-open entry timing; benchmark remains continuously long thereafter"
            ),
        },
        # Keep the pre-1.1 strategy result fields at results.* for compatibility.
        "results": strategy,
        "benchmark": benchmark,
        "forward_horizon": (
            evaluate_forward_horizon(candles, horizon_bars=24)
            if len(candles) > 24 else None
        ),
        "comparison": {
            "strategy_minus_benchmark_return_pct": (
                strategy["net_return_pct"] - benchmark["net_return_pct"]
            ),
        },
        "evaluation_generated_at_utc": (
            datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        ),
    }


def write_report(report: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
