"""BTC signal lab paper-trading analysis primitives."""
from .aggregator import aggregate_signals
from .paper_trading import PaperTrader
from .signal_engine import atr, ema, generate_signal, macd, rsi, to_json

__all__ = [
    "PaperTrader",
    "aggregate_signals",
    "atr",
    "ema",
    "generate_signal",
    "macd",
    "rsi",
    "to_json",
]
