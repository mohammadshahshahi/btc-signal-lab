"""Deterministic, long-only-independent technical signal engine for paper trading.

No exchange clients, order execution, credentials, or network access are used.
Input candles are chronological (oldest first) OHLC mappings with finite numbers.
"""
from __future__ import annotations

from math import isfinite
from typing import Any, Iterable, Mapping, Sequence

Candle = Mapping[str, Any]


def _number(value: Any, field: str, index: int) -> float:
    if isinstance(value, bool):
        raise ValueError(f"candle[{index}].{field} must be numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"candle[{index}].{field} must be numeric") from exc
    if not isfinite(result):
        raise ValueError(f"candle[{index}].{field} must be finite")
    return result


def _validate_candles(candles: Sequence[Candle]) -> tuple[list[float], list[float], list[float]]:
    if not isinstance(candles, Sequence) or isinstance(candles, (str, bytes)):
        raise TypeError("candles must be a sequence of OHLC mappings")
    if not candles:
        raise ValueError("candles must not be empty")
    highs: list[float] = []
    lows: list[float] = []
    closes: list[float] = []
    for i, candle in enumerate(candles):
        if not isinstance(candle, Mapping):
            raise TypeError(f"candle[{i}] must be a mapping")
        missing = {"high", "low", "close"} - candle.keys()
        if missing:
            raise ValueError(f"candle[{i}] missing required fields: {', '.join(sorted(missing))}")
        high = _number(candle["high"], "high", i)
        low = _number(candle["low"], "low", i)
        close = _number(candle["close"], "close", i)
        if high < low:
            raise ValueError(f"candle[{i}].high must be >= low")
        if not low <= close <= high:
            raise ValueError(f"candle[{i}].close must be between low and high")
        highs.append(high)
        lows.append(low)
        closes.append(close)
    return highs, lows, closes


def ema(values: Sequence[float], period: int) -> list[float | None]:
    """EMA seeded by the first period's SMA; earlier positions are None."""
    if period < 1:
        raise ValueError("period must be >= 1")
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    seed = sum(float(v) for v in values[:period]) / period
    out[period - 1] = seed
    alpha = 2.0 / (period + 1.0)
    current = seed
    for i in range(period, len(values)):
        current = alpha * float(values[i]) + (1.0 - alpha) * current
        out[i] = current
    return out


def rsi(values: Sequence[float], period: int = 14) -> list[float | None]:
    """Wilder RSI. The first value is at index period; flat series yields 50."""
    if period < 1:
        raise ValueError("period must be >= 1")
    out: list[float | None] = [None] * len(values)
    if len(values) <= period:
        return out
    gains = [max(float(values[i]) - float(values[i - 1]), 0.0) for i in range(1, len(values))]
    losses = [max(float(values[i - 1]) - float(values[i]), 0.0) for i in range(1, len(values))]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    def value(gain: float, loss: float) -> float:
        if gain == 0.0 and loss == 0.0:
            return 50.0
        if loss == 0.0:
            return 100.0
        if gain == 0.0:
            return 0.0
        return 100.0 - 100.0 / (1.0 + gain / loss)

    out[period] = value(avg_gain, avg_loss)
    for i in range(period + 1, len(values)):
        delta_index = i - 1
        avg_gain = (avg_gain * (period - 1) + gains[delta_index]) / period
        avg_loss = (avg_loss * (period - 1) + losses[delta_index]) / period
        out[i] = value(avg_gain, avg_loss)
    return out


def macd(
    values: Sequence[float], fast_period: int = 12, slow_period: int = 26, signal_period: int = 9
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """Return MACD line, signal line, histogram; SMA-seeded component EMAs."""
    if min(fast_period, slow_period, signal_period) < 1:
        raise ValueError("MACD periods must be >= 1")
    if fast_period >= slow_period:
        raise ValueError("fast_period must be less than slow_period")
    fast = ema(values, fast_period)
    slow = ema(values, slow_period)
    line: list[float | None] = [None] * len(values)
    for i, (f, s) in enumerate(zip(fast, slow)):
        if f is not None and s is not None:
            line[i] = f - s
    valid_indices = [i for i, item in enumerate(line) if item is not None]
    signal: list[float | None] = [None] * len(values)
    hist: list[float | None] = [None] * len(values)
    if len(valid_indices) < signal_period:
        return line, signal, hist
    valid_line = [float(line[i]) for i in valid_indices]
    valid_signal = ema(valid_line, signal_period)
    for j, i in enumerate(valid_indices):
        sig = valid_signal[j]
        if sig is not None:
            signal[i] = sig
            hist[i] = float(line[i]) - sig
    return line, signal, hist


def atr(candles: Sequence[Candle], period: int = 14) -> list[float | None]:
    """Wilder ATR; first value is the SMA of the first period true ranges."""
    if period < 1:
        raise ValueError("period must be >= 1")
    highs, lows, closes = _validate_candles(candles)
    out: list[float | None] = [None] * len(candles)
    if len(candles) < period:
        return out
    true_ranges: list[float] = []
    for i, (high, low) in enumerate(zip(highs, lows)):
        if i == 0:
            true_ranges.append(high - low)
        else:
            true_ranges.append(max(high - low, abs(high - closes[i - 1]), abs(low - closes[i - 1])))
    current = sum(true_ranges[:period]) / period
    out[period - 1] = current
    for i in range(period, len(candles)):
        current = (current * (period - 1) + true_ranges[i]) / period
        out[i] = current
    return out


def _latest(values: Sequence[float | None]) -> float | None:
    return values[-1] if values else None


def generate_signal(
    candles: Sequence[Candle],
    *,
    symbol: str = "BTC/USDT",
    timeframe: str = "1h",
) -> dict[str, Any]:
    """Calculate indicators and return a JSON-serializable BUY/SELL/HOLD snapshot.

    BUY requires close > EMA20 > EMA50, MACD > signal, positive histogram,
    and RSI in [50, 70]. SELL mirrors this with close < EMA20 < EMA50,
    MACD < signal, negative histogram, and RSI in [30, 50]. Otherwise HOLD.
    These are baseline rules, not investment advice or a profitability claim.
    """
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("symbol must be a non-empty string")
    if not isinstance(timeframe, str) or not timeframe.strip():
        raise ValueError("timeframe must be a non-empty string")
    highs, lows, closes = _validate_candles(candles)
    ema20 = ema(closes, 20)
    ema50 = ema(closes, 50)
    rsi14 = rsi(closes, 14)
    macd_line, macd_signal, macd_hist = macd(closes)
    atr14 = atr(candles, 14)
    values = {
        "ema20": _latest(ema20),
        "ema50": _latest(ema50),
        "rsi14": _latest(rsi14),
        "macd": _latest(macd_line),
        "macd_signal": _latest(macd_signal),
        "macd_histogram": _latest(macd_hist),
        "atr14": _latest(atr14),
    }
    ready = all(value is not None and isfinite(value) for value in values.values())
    close = closes[-1]
    signal = "HOLD"
    reasons: list[str] = []
    if not ready:
        reasons.append("insufficient_history")
    else:
        e20 = float(values["ema20"])
        e50 = float(values["ema50"])
        r = float(values["rsi14"])
        m = float(values["macd"])
        ms = float(values["macd_signal"])
        mh = float(values["macd_histogram"])
        if close > e20 > e50 and m > ms and mh > 0 and 50 <= r <= 70:
            signal = "BUY"
            reasons.append("bullish_trend_momentum")
        elif close < e20 < e50 and m < ms and mh < 0 and 30 <= r <= 50:
            signal = "SELL"
            reasons.append("bearish_trend_momentum")
        else:
            reasons.append("criteria_not_met")
    return {
        "schema_version": "1.0",
        "mode": "paper_trading",
        "symbol": symbol.strip().upper(),
        "timeframe": timeframe.strip(),
        "signal": signal,
        "price": close,
        "indicators": values,
        "reasons": reasons,
    }


def to_json(signal: Mapping[str, Any]) -> str:
    """Serialize a signal deterministically; reject NaN/Infinity."""
    import json
    return json.dumps(signal, allow_nan=False, sort_keys=True, separators=(",", ":"))
