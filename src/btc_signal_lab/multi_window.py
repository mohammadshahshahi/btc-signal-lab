"""Deterministic orchestration for pre-registered multi-window evaluations.

This module consumes only local, frozen CSV/manifest pairs. It never downloads
market data or changes Signal Engine parameters.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .evaluation import evaluate_dataset
from .market_data import parse_utc


def _flat_baseline(initial_capital: float) -> dict[str, Any]:
    return {
        "mode": "historical_benchmark",
        "benchmark": "flat_cash_no_trade",
        "initial_capital": initial_capital,
        "final_equity": initial_capital,
        "net_profit": 0.0,
        "net_return_pct": 0.0,
        "max_drawdown_pct": 0.0,
        "trade_count": 0,
        "win_rate_pct": 0.0,
        "profit_factor": None,
        "average_trade_pnl": 0.0,
        "average_trade_return_pct": 0.0,
        "average_holding_bars": 0.0,
        "exposure_pct": 0.0,
        "fee_rate": 0.0,
        "slippage_bps": 0.0,
        "limitations": ["Cash-only comparator; no trades and no market exposure."],
    }


def evaluate_windows(
    windows: Sequence[Mapping[str, Any]],
    *,
    code_commit: str,
    initial_capital: float = 10_000.0,
    fee_rate: float = 0.001,
    slippage_bps: float = 5.0,
) -> dict[str, Any]:
    """Evaluate explicitly ordered frozen datasets and return deterministic JSON data.

    Each window requires: name, partition (train/validation/test), csv_path,
    interval, start_utc, and end_utc_exclusive. The supplied order must be
    chronological and non-overlapping. A test partition, if present, must be
    unique and last. The caller is responsible for obtaining dual approval
    before supplying any held-out test dataset.
    """
    if not isinstance(windows, Sequence) or isinstance(windows, (str, bytes)):
        raise TypeError("windows must be a sequence")
    if not windows:
        raise ValueError("at least one evaluation window is required")
    if not isinstance(code_commit, str) or not code_commit.strip():
        raise ValueError("code_commit must be a non-empty commit identifier")

    seen_names: set[str] = set()
    normalized: list[dict[str, Any]] = []
    previous_end = None
    test_indexes: list[int] = []

    for index, spec in enumerate(windows):
        if not isinstance(spec, Mapping):
            raise TypeError(f"windows[{index}] must be a mapping")
        required = {"name", "partition", "csv_path", "interval", "start_utc", "end_utc_exclusive"}
        missing = required - spec.keys()
        if missing:
            raise ValueError(f"windows[{index}] missing fields: {', '.join(sorted(missing))}")

        name = spec["name"]
        partition = spec["partition"]
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"windows[{index}].name must be non-empty")
        if name in seen_names:
            raise ValueError(f"duplicate window name: {name}")
        seen_names.add(name)
        if partition not in {"train", "validation", "test"}:
            raise ValueError(f"windows[{index}].partition must be train, validation, or test")
        if partition == "test":
            test_indexes.append(index)

        start = parse_utc(spec["start_utc"])
        end = parse_utc(spec["end_utc_exclusive"])
        if end <= start:
            raise ValueError(f"window {name} end must be later than start")
        if previous_end is not None and start < previous_end:
            raise ValueError("windows must be supplied in chronological, non-overlapping order")
        previous_end = end

        interval = spec["interval"]
        if interval not in {"1h", "4h"}:
            raise ValueError(f"window {name} interval must be 1h or 4h")

        normalized.append({
            "name": name,
            "partition": partition,
            "csv_path": str(Path(spec["csv_path"])),
            "interval": interval,
            "start_utc": start.isoformat().replace("+00:00", "Z"),
            "end_utc_exclusive": end.isoformat().replace("+00:00", "Z"),
        })

    if len(test_indexes) > 1:
        raise ValueError("at most one final test partition is allowed per evaluation run")
    if test_indexes and test_indexes[0] != len(normalized) - 1:
        raise ValueError("the final test partition must be the last chronological window")

    reports: list[dict[str, Any]] = []
    for spec in normalized:
        report = evaluate_dataset(
            spec["csv_path"],
            initial_capital=initial_capital,
            fee_rate=fee_rate,
            slippage_bps=slippage_bps,
        )
        dataset = report["dataset"]
        expected = {
            "symbol": "BTCUSDT",
            "interval": spec["interval"],
            "start_utc": spec["start_utc"],
            "end_utc_exclusive": spec["end_utc_exclusive"],
        }
        for key, value in expected.items():
            if dataset.get(key) != value:
                raise ValueError(
                    f"window {spec['name']} manifest {key} mismatch: "
                    f"expected {value!r}, received {dataset.get(key)!r}"
                )

        # The single-dataset evaluator adds a wall-clock generation timestamp.
        # Remove it so identical inputs produce byte-for-byte identical reports.
        report.pop("evaluation_generated_at_utc", None)
        reports.append({
            "window": {key: spec[key] for key in (
                "name", "partition", "interval", "start_utc", "end_utc_exclusive"
            )},
            "dataset": dataset,
            "assumptions": report["assumptions"],
            "strategy": report["results"],
            "buy_and_hold": report["benchmark"],
            "flat_cash": _flat_baseline(initial_capital),
            "forward_horizon_diagnostics": {
                "classification": "directional diagnostic; not fill-level PnL",
                "metrics": report["forward_horizon"],
            },
            "comparison": {
                "strategy_minus_buy_and_hold_return_pct":
                    report["comparison"]["strategy_minus_benchmark_return_pct"],
                "strategy_minus_flat_return_pct": report["results"]["net_return_pct"],
            },
        })

    return {
        "report_schema_version": "1.0",
        "evaluation_type": "multi_window_paper_research",
        "code_commit": code_commit,
        "parameters": {
            "initial_capital": initial_capital,
            "fee_rate_per_side": fee_rate,
            "slippage_bps_per_side": slippage_bps,
            "signal_engine": "v1.1; existing weights and thresholds unchanged",
        },
        "determinism": {
            "runtime_timestamps_excluded": True,
            "input_window_order_preserved": True,
            "network_access": False,
        },
        "windows": reports,
        "limitations": [
            "Research and paper trading only; no live orders or credentials.",
            "Signal direction diagnostics are separate from fill-level backtest PnL.",
            "Forward-horizon observations overlap and are not independent.",
            "Execution is long-only with next-candle-open fills.",
            "Fees and fixed slippage are assumptions; spread, funding, market impact, outages, and partial fills are excluded.",
            "A historical test window is untouched only if its data/results were not previously inspected or used for decisions.",
        ],
    }


def write_multi_window_report(report: Mapping[str, Any], output_path: str | Path) -> None:
    """Write a stable, sorted JSON report; no wall-clock metadata is injected."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
