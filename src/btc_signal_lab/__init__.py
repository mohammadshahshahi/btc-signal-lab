"""BTC signal lab paper-trading analysis primitives."""
from .aggregator import aggregate_signals
from .paper_trading import PaperTrader
from .horizon_evaluator import evaluate_forward_horizon
from .signal_engine import atr, ema, generate_signal, macd, rsi, to_json, volume_indicators

__all__ = [
    "PaperTrader",
    "aggregate_signals",
    "atr",
    "ema",
    "generate_signal",
    "evaluate_forward_horizon",
    "macd",
    "rsi",
    "to_json",
    "volume_indicators",
]
