"""Credential-free spot paper trading ledger; never submits real orders."""
from __future__ import annotations

from datetime import datetime
from math import isfinite
from typing import Any


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _validate_timestamp(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamp must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.isoformat()


class PaperTrader:
    """All-in/all-out long-only paper portfolio with fees and adverse slippage.

    Call execute() only with a price available at the intended simulated fill
    time (normally the next candle open). This class has no network dependency.
    """

    def __init__(
        self,
        *,
        initial_cash: float = 10_000.0,
        fee_rate: float = 0.001,
        slippage_bps: float = 5.0,
    ) -> None:
        self.initial_cash = _finite(initial_cash, "initial_cash")
        self.fee_rate = _finite(fee_rate, "fee_rate")
        self.slippage_bps = _finite(slippage_bps, "slippage_bps")
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if not 0.0 <= self.fee_rate < 1.0:
            raise ValueError("fee_rate must be in [0, 1)")
        if not 0.0 <= self.slippage_bps < 10_000.0:
            raise ValueError("slippage_bps must be in [0, 10000)")

        self.cash = self.initial_cash
        self.quantity = 0.0
        self.position: dict[str, Any] | None = None
        self.trades: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []

    def execute(self, signal: str, price: float, timestamp: str) -> dict[str, Any]:
        """Apply BUY/SELL/HOLD at the supplied simulated execution price."""
        if signal not in {"BUY", "SELL", "HOLD"}:
            raise ValueError("signal must be BUY, SELL, or HOLD")
        market_price = _finite(price, "price")
        if market_price <= 0:
            raise ValueError("price must be positive")
        stamp = _validate_timestamp(timestamp)
        slip = self.slippage_bps / 10_000.0
        action = "HOLD"

        if signal == "BUY" and self.position is None:
            fill = market_price * (1.0 + slip)
            quantity = self.cash / (fill * (1.0 + self.fee_rate))
            fee = quantity * fill * self.fee_rate
            cost_basis = quantity * fill + fee
            self.position = {
                "entry_timestamp": stamp,
                "entry_market_price": market_price,
                "entry_fill_price": fill,
                "quantity": quantity,
                "entry_fee": fee,
                "cost_basis": cost_basis,
            }
            self.cash = 0.0
            self.quantity = quantity
            action = "OPEN_LONG"

        elif signal == "SELL" and self.position is not None:
            fill = market_price * (1.0 - slip)
            gross = self.quantity * fill
            fee = gross * self.fee_rate
            proceeds = gross - fee
            trade = {
                "entry_timestamp": self.position["entry_timestamp"],
                "exit_timestamp": stamp,
                "entry_price": self.position["entry_fill_price"],
                "exit_market_price": market_price,
                "exit_price": fill,
                "quantity": self.quantity,
                "entry_fee": self.position["entry_fee"],
                "exit_fee": fee,
                "cost_basis": self.position["cost_basis"],
                "net_pnl": proceeds - self.position["cost_basis"],
                "net_return_pct": (
                    (proceeds / self.position["cost_basis"] - 1.0) * 100.0
                ),
            }
            self.trades.append(trade)
            self.cash = proceeds
            self.quantity = 0.0
            self.position = None
            action = "CLOSE_LONG"

        event = {
            "timestamp": stamp,
            "signal": signal,
            "market_price": market_price,
            "action": action,
            "cash": self.cash,
            "quantity": self.quantity,
        }
        self.events.append(event)
        return dict(event)

    def equity(self, mark_price: float) -> float:
        """Return estimated net liquidation equity at a mark price."""
        mark = _finite(mark_price, "mark_price")
        if mark <= 0:
            raise ValueError("mark_price must be positive")
        if self.position is None:
            return self.cash
        liquidation = mark * (1.0 - self.slippage_bps / 10_000.0)
        return self.quantity * liquidation * (1.0 - self.fee_rate)

    def snapshot(self, mark_price: float) -> dict[str, Any]:
        """Return a JSON-serializable portfolio snapshot."""
        return {
            "schema_version": "1.0",
            "mode": "paper_trading",
            "initial_cash": self.initial_cash,
            "cash": self.cash,
            "quantity": self.quantity,
            "position": dict(self.position) if self.position else None,
            "equity": self.equity(mark_price),
            "realized_net_pnl": sum(trade["net_pnl"] for trade in self.trades),
            "trade_count": len(self.trades),
            "trades": [dict(trade) for trade in self.trades],
            "events": [dict(event) for event in self.events],
            "live_orders_submitted": 0,
        }
