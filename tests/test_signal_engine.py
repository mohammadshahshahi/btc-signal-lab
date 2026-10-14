import json
import math
import unittest
from unittest.mock import patch

import btc_signal_lab.signal_engine as engine

from btc_signal_lab.signal_engine import atr, ema, generate_signal, macd, rsi, to_json


def candles_from_closes(closes):
    # Valid synthetic OHLC candles with a small range around each close.
    return [
        {"high": float(c) + 1.0, "low": float(c) - 1.0, "close": float(c)}
        for c in closes
    ]


class IndicatorTests(unittest.TestCase):
    def test_ema_sma_seed_and_warmup(self):
        self.assertEqual(ema([1, 2, 3, 4], 3), [None, None, 2.0, 3.0])

    def test_ema_rejects_invalid_period(self):
        with self.assertRaises(ValueError):
            ema([1, 2], 0)

    def test_indicators_reject_non_finite_values(self):
        for indicator in (ema, rsi):
            with self.subTest(indicator=indicator.__name__):
                with self.assertRaises(ValueError):
                    indicator([1.0, math.inf, 3.0], 2)
        with self.assertRaises(ValueError):
            macd([1.0, 2.0, math.nan], fast_period=1, slow_period=2, signal_period=1)

    def test_indicators_require_positive_integer_periods(self):
        for bad_period in (0, -1, 1.5, True):
            with self.subTest(period=bad_period):
                with self.assertRaises(ValueError):
                    ema([1.0, 2.0], bad_period)
        with self.assertRaises(ValueError):
            atr(candles_from_closes([1.0, 2.0]), 1.5)

    def test_rsi_up_only_and_down_only(self):
        self.assertEqual(rsi([1, 2, 3, 4], 2)[2], 100.0)
        self.assertEqual(rsi([4, 3, 2, 1], 2)[2], 0.0)

    def test_rsi_flat_series_is_neutral(self):
        self.assertEqual(rsi([5, 5, 5, 5], 2)[2], 50.0)

    def test_rsi_warmup(self):
        self.assertEqual(rsi([1, 2, 3], 3), [None, None, None])

    def test_macd_warmup_and_lengths(self):
        line, sig, hist = macd([float(i) for i in range(40)])
        self.assertEqual(len(line), 40)
        self.assertIsNone(line[24])
        self.assertIsNotNone(line[25])
        self.assertIsNone(sig[32])
        self.assertIsNotNone(sig[33])
        self.assertAlmostEqual(hist[39], line[39] - sig[39])

    def test_atr_wilder_and_warmup(self):
        data = [
            {"high": 10, "low": 8, "close": 9},
            {"high": 12, "low": 9, "close": 11},
            {"high": 13, "low": 10, "close": 12},
        ]
        result = atr(data, 2)
        self.assertIsNone(result[0])
        self.assertAlmostEqual(result[1], 2.5)
        self.assertAlmostEqual(result[2], 2.75)

    def test_signal_contract_is_json_serializable_and_paper_only(self):
        result = generate_signal(candles_from_closes(range(1, 61)))
        self.assertEqual(result["schema_version"], "1.1")
        self.assertEqual(result["mode"], "paper_trading")
        self.assertIn(result["signal"], {"BUY", "SELL", "HOLD"})
        self.assertIn(result["direction"], {"LONG", "SHORT", "NEUTRAL"})
        self.assertGreaterEqual(result["score"], 0.0)
        self.assertLessEqual(result["score"], 100.0)
        self.assertEqual(result["score_thresholds"], {"long": 70.0, "short": 30.0})
        self.assertEqual(result["symbol"], "BTC/USDT")
        self.assertEqual(set(result["indicators"]), {
            "ema20", "ema50", "rsi14", "macd", "macd_signal",
            "macd_histogram", "atr14", "volume_sma20", "volume_ratio"
        })
        self.assertEqual(json.loads(to_json(result)), result)


    def test_buy_signal_requires_all_bullish_conditions(self):
        data = candles_from_closes([130.0] * 50)

        def fake_ema(values, period):
            last = 120.0 if period == 20 else 110.0
            return [None] * (len(values) - 1) + [last]

        def fake_rsi(values, period=14):
            return [None] * (len(values) - 1) + [60.0]

        def fake_macd(values, fast_period=12, slow_period=26, signal_period=9):
            return (
                [None] * (len(values) - 1) + [2.0],
                [None] * (len(values) - 1) + [1.0],
                [None] * (len(values) - 1) + [1.0],
            )

        with (
            patch.object(engine, "ema", side_effect=fake_ema),
            patch.object(engine, "rsi", side_effect=fake_rsi),
            patch.object(engine, "macd", side_effect=fake_macd),
            patch.object(engine, "atr", return_value=[None] * 49 + [2.0]),
        ):
            result = engine.generate_signal(data)
        self.assertEqual(result["signal"], "BUY")
        self.assertEqual(result["reasons"], ["bullish_score_threshold"])
        self.assertEqual(result["direction"], "LONG")
        self.assertGreaterEqual(result["score"], 70.0)

    def test_sell_signal_requires_all_bearish_conditions(self):
        data = candles_from_closes([80.0] * 50)

        def fake_ema(values, period):
            last = 90.0 if period == 20 else 100.0
            return [None] * (len(values) - 1) + [last]

        def fake_rsi(values, period=14):
            return [None] * (len(values) - 1) + [40.0]

        def fake_macd(values, fast_period=12, slow_period=26, signal_period=9):
            return (
                [None] * (len(values) - 1) + [-2.0],
                [None] * (len(values) - 1) + [-1.0],
                [None] * (len(values) - 1) + [-1.0],
            )

        with (
            patch.object(engine, "ema", side_effect=fake_ema),
            patch.object(engine, "rsi", side_effect=fake_rsi),
            patch.object(engine, "macd", side_effect=fake_macd),
            patch.object(engine, "atr", return_value=[None] * 49 + [2.0]),
        ):
            result = engine.generate_signal(data)
        self.assertEqual(result["signal"], "SELL")
        self.assertEqual(result["reasons"], ["bearish_score_threshold"])
        self.assertEqual(result["direction"], "SHORT")
        self.assertLessEqual(result["score"], 30.0)

    def test_insufficient_history_fails_closed_to_hold(self):
        result = generate_signal(candles_from_closes(range(1, 30)))
        self.assertEqual(result["signal"], "HOLD")
        self.assertEqual(result["direction"], "NEUTRAL")
        self.assertEqual(result["score"], 50.0)
        self.assertIn("insufficient_history", result["reasons"])
        self.assertIsNone(result["indicators"]["ema50"])
        self.assertIsNone(result["indicators"]["macd_signal"])
        self.assertIsNotNone(result["indicators"]["rsi14"])
        self.assertIsNotNone(result["indicators"]["atr14"])

    def test_flat_market_scores_neutral(self):
        result = generate_signal(candles_from_closes([100.0] * 60))
        self.assertEqual(result["signal"], "HOLD")
        self.assertEqual(result["direction"], "NEUTRAL")
        self.assertEqual(result["score"], 50.0)

    def test_invalid_candle_values_are_rejected(self):
        with self.assertRaises(ValueError):
            generate_signal([{"high": 1, "low": 2, "close": 1.5}])
        with self.assertRaises(ValueError):
            generate_signal([{"high": math.nan, "low": 0, "close": 0}])

    def test_required_fields_are_checked(self):
        with self.assertRaises(ValueError):
            generate_signal([{"close": 1, "high": 2}])

    def test_optional_volume_metrics_are_reported(self):
        data = [
            {"high": float(i + 2), "low": float(i), "close": float(i + 1), "volume": float(i + 1)}
            for i in range(1, 61)
        ]
        result = generate_signal(data)
        self.assertAlmostEqual(result["indicators"]["volume_sma20"], 51.5)
        self.assertGreater(result["indicators"]["volume_ratio"], 0)

    def test_volume_must_be_consistent_and_non_negative(self):
        data = candles_from_closes(range(1, 25))
        data[-1]["volume"] = 10
        with self.assertRaises(ValueError):
            generate_signal(data)
        invalid = candles_from_closes(range(1, 25))
        for candle in invalid:
            candle["volume"] = 1
        invalid[-1]["volume"] = -1
        with self.assertRaises(ValueError):
            generate_signal(invalid)

    def test_symbol_and_timeframe_are_checked(self):
        data = candles_from_closes(range(1, 5))
        with self.assertRaises(ValueError):
            generate_signal(data, symbol=" ")
        with self.assertRaises(ValueError):
            generate_signal(data, timeframe="")


if __name__ == "__main__":
    unittest.main()
