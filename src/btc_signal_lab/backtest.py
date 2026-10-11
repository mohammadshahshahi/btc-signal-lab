"""Leakage-aware, long-only historical backtest for paper-trading signals.

Signals are computed using candles through the current close and executed no
earlier than the next candle open. This module never connects to an exchange.
"""
from __future__ import annotations

from math import isfinite
from typing import Any, Callable, Mapping, Sequence

from .signal_engine import generate_signal

Candle = Mapping[str, Any]
SignalFunction = Callable[[Sequence[Candle]], Mapping[str, Any]]


def _finite_number(value: Any, field: str, index: int) -> float:
    if isinstance(value, bool):
        raise ValueError(f"candle[{index}].{field} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"candle[{index}].{field} must be numeric") from exc
    if not isfinite(number):
        raise ValueError(f"candle[{index}].{field} must be finite")
    return number


def _validate(candles: Sequence[Candle]) -> list[dict[str, Any]]:
    if not isinstance(candles, Sequence) or isinstance(candles, (str, bytes)):
        raise TypeError("candles must be a sequence")
    if len(candles) < 2:
        raise ValueError("at least two candles are required")
    result: list[dict[str, Any]] = []
    for i, candle in enumerate(candles):
        if not isinstance(candle, Mapping):
            raise TypeError(f"candle[{i}] must be a mapping")
        missing = {"open", "high", "low", "close"} - candle.keys()
        if missing:
            raise ValueError(f"candle[{i}] missing required fields: {', '.join(sorted(missing))}")
        item = {key: _finite_number(candle[key], key, i) for key in ("open", "high", "low", "close")}
        if item["high"] < item["low"]:
            raise ValueError(f"candle[{i}].high must be >= low")
        if not item["low"] <= item["open"] <= item["high"]:
            raise ValueError(f"candle[{i}].open must be between low and high")
        if not item["low"] <= item["close"] <= item["high"]:
            raise ValueError(f"candle[{i}].close must be between low and high")
        if "timestamp" in candle:
            item["timestamp"] = candle["timestamp"]
        result.append(item)
    return result


def run_backtest(
    candles: Sequence[Candle],
    *,
    initial_capital: float = 10_000.0,
    fee_rate: float = 0.001,
    slippage_bps: float = 5.0,
    signal_fn: SignalFunction | None = None,
) -> dict[str, Any]:
    """Backtest a long-only BUY/SELL strategy with costs and next-open fills.

    A BUY opens a position only when flat; SELL closes it only when long.
    Any remaining position is liquidated at the final close. Rates are
    fractions (fee_rate=0.001 means 0.1%) and slippage is in basis points.
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
    if signal_fn is None:
        signal_fn = lambda history: generate_signal(history)

    cash = initial_capital
    quantity = 0.0
    entry_price: float | None = None
    entry_index: int | None = None
    entry_fee = 0.0
    trades: list[dict[str, Any]] = []
    equity_curve: list[dict[str, Any]] = []
    peak_equity = initial_capital
    max_drawdown = 0.0
    slip = slippage_bps / 10_000.0

    def mark_equity(reference_price: float) -> float:
        if quantity <= 0:
            return cash
        liquidation_price = reference_price * (1.0 - slip)
        return cash + quantity * liquidation_price * (1.0 - fee_rate)

    def close_position(reference_price: float, index: int, reason: str) -> None:
        nonlocal cash, quantity, entry_price, entry_index, entry_fee
        fill = reference_price * (1.0 - slip)
        exit_fee = quantity * fill * fee_rate
        proceeds = quantity * fill - exit_fee
        cash += proceeds
        pnl = proceeds - (quantity * float(entry_price) + entry_fee)
        trade = {
            "entry_index": entry_index,
            "exit_index": index,
            "entry_timestamp": data[int(entry_index)].get("timestamp"),
            "exit_timestamp": data[index].get("timestamp"),
            "entry_price": entry_price,
            "exit_price": fill,
            "quantity": quantity,
            "entry_fee": entry_fee,
            "exit_fee": exit_fee,
            "net_pnl": pnl,
            "exit_reason": reason,
        }
        trades.append(trade)
        quantity = 0.0
        entry_price = None
        entry_index = None
        entry_fee = 0.0

    # Record initial mark, then process each close-generated signal at the
    # following candle open before marking that candle's close.
    first_equity = mark_equity(data[0]["close"])
    equity_curve.append({
        "index": 0,
        "timestamp": data[0].get("timestamp"),
        "equity": first_equity,
        "drawdown": 0.0,
    })
    for i in range(len(data) - 1):
        signal = signal_fn(data[: i + 1]).get("signal")
        next_index = i + 1
        next_candle = data[next_index]
        if signal == "BUY" and quantity == 0.0:
            fill = next_candle["open"] * (1.0 + slip)
            quantity = cash / (fill * (1.0 + fee_rate))
            entry_fee = quantity * fill * fee_rate
            cash = 0.0
            entry_price = fill
            entry_index = next_index
        elif signal == "SELL" and quantity > 0.0:
            close_position(next_candle["open"], next_index, "sell_signal")

        equity = mark_equity(next_candle["close"])
        peak_equity = max(peak_equity, equity)
        drawdown = (peak_equity - equity) / peak_equity if peak_equity else 0.0
        max_drawdown = max(max_drawdown, drawdown)
        equity_curve.append({
            "index": next_index,
            "timestamp": next_candle.get("timestamp"),
            "equity": equity,
            "drawdown": drawdown,
        })

    if quantity > 0.0:
        close_position(data[-1]["close"], len(data) - 1, "end_of_data")
        final_equity = cash
        equity_curve[-1]["equity"] = final_equity
        peak_equity = max(peak_equity, final_equity)
        equity_curve[-1]["drawdown"] = (peak_equity - final_equity) / peak_equity
        max_drawdown = max(max_drawdown, equity_curve[-1]["drawdown"])

    final_equity = cash
    net_return = final_equity / initial_capital - 1.0
    wins = sum(1 for trade in trades if trade["net_pnl"] > 0)
    return {
        "mode": "historical_backtest",
        "strategy": "long_only_next_open",
        "initial_capital": initial_capital,
        "final_equity": final_equity,
        "net_profit": final_equity - initial_capital,
        "net_return_pct": net_return * 100.0,
        "max_drawdown_pct": max_drawdown * 100.0,
        "trade_count": len(trades),
        "win_rate_pct": (wins / len(trades) * 100.0) if trades else 0.0,
        "fee_rate": fee_rate,
        "slippage_bps": slippage_bps,
        "trades": trades,
        "equity_curve": equity_curve,
        "limitations": [
            "Long-only baseline; SELL closes a long position and does not open a short.",
            "Signals use close data through the signal candle; fills occur at the next candle open.",
            "No funding, spread model, exchange outages, partial fills, or intrabar stop execution.",
            "Historical performance is not a guarantee of future results.",
        ],
    }
