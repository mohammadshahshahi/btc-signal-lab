"""Cost-aware buy-and-hold comparator for historical OHLCV candles."""
from __future__ import annotations

from math import isfinite
from typing import Any, Mapping, Sequence

from .backtest import _finite_number, _validate

Candle = Mapping[str, Any]


def run_buy_and_hold(
    candles: Sequence[Candle],
    *,
    initial_capital: float = 10_000.0,
    fee_rate: float = 0.001,
    slippage_bps: float = 5.0,
) -> dict[str, Any]:
    """Buy at the second candle's open and liquidate at the last candle's close.

    Entry timing matches the earliest possible next-open strategy execution.
    The benchmark is fully invested, long-only, and applies fee and slippage
    on both entry and exit. It is a comparator, not a strategy signal.
    """
    data = _validate(candles)
    initial_capital = _finite_number(initial_capital, "initial_capital", 0)
    fee_rate = _finite_number(fee_rate, "fee_rate", 0)
    slippage_bps = _finite_number(slippage_bps, "slippage_bps", 0)
    if initial_capital <= 0:
        raise ValueError("initial_capital must be positive")
    if not 0 <= fee_rate < 1:
        raise ValueError("fee_rate must be in [0, 1)")
    if not 0 <= slippage_bps < 10_000:
        raise ValueError("slippage_bps must be in [0, 10000)")

    slip = slippage_bps / 10_000.0
    entry_index = 1
    entry_price = data[entry_index]["open"] * (1.0 + slip)
    quantity = initial_capital / (entry_price * (1.0 + fee_rate))
    entry_fee = quantity * entry_price * fee_rate
    exit_price = data[-1]["close"] * (1.0 - slip)
    exit_fee = quantity * exit_price * fee_rate
    final_equity = quantity * exit_price - exit_fee

    curve: list[dict[str, Any]] = []
    peak = initial_capital
    max_drawdown = 0.0
    for i, candle in enumerate(data):
        if i < entry_index:
            equity = initial_capital
        else:
            liquidation_price = candle["close"] * (1.0 - slip)
            equity = quantity * liquidation_price * (1.0 - fee_rate)
        if i == len(data) - 1:
            equity = final_equity
        peak = max(peak, equity)
        drawdown = (peak - equity) / peak if peak else 0.0
        max_drawdown = max(max_drawdown, drawdown)
        curve.append({
            "index": i,
            "timestamp": candle.get("timestamp"),
            "equity": equity,
            "drawdown": drawdown,
        })

    return {
        "mode": "historical_benchmark",
        "benchmark": "buy_and_hold_long",
        "initial_capital": initial_capital,
        "entry_index": entry_index,
        "exit_index": len(data) - 1,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "quantity": quantity,
        "entry_fee": entry_fee,
        "exit_fee": exit_fee,
        "final_equity": final_equity,
        "net_profit": final_equity - initial_capital,
        "net_return_pct": (final_equity / initial_capital - 1.0) * 100.0,
        "max_drawdown_pct": max_drawdown * 100.0,
        "fee_rate": fee_rate,
        "slippage_bps": slippage_bps,
        "equity_curve": curve,
        "limitations": [
            "Fully invested long-only benchmark; no cash allocation or signal timing.",
            "Entry uses the second candle open and exit uses the final candle close.",
            "Fees and fixed slippage are modeled; spread, funding, outages, and partial fills are not.",
        ],
    }
