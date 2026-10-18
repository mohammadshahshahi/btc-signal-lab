import unittest

from btc_signal_lab.horizon_evaluator import evaluate_forward_horizon


def candles(closes):
    return [
        {
            "timestamp": f"2026-10-01T{index:02d}:00:00Z",
            "open": float(close),
            "high": float(close) + 1,
            "low": float(close) - 1,
            "close": float(close),
            "idx": index,
        }
        for index, close in enumerate(closes)
    ]


class ForwardHorizonTests(unittest.TestCase):
    def test_directional_metrics_and_neutral_coverage(self):
        data = candles([100, 101, 102, 101, 100, 99, 100])
        directions = {
            0: "LONG",
            1: "NEUTRAL",
            2: "SHORT",
            3: "SHORT",
            4: "LONG",
        }
        seen_lengths = []

        def signal_fn(history):
            seen_lengths.append(len(history))
            return {"direction": directions[history[-1]["idx"]], "score": 50}

        result = evaluate_forward_horizon(data, horizon_bars=2, signal_fn=signal_fn)
        self.assertEqual(seen_lengths, [1, 2, 3, 4, 5])
        self.assertEqual(result["observation_count"], 5)
        self.assertEqual(result["actionable_count"], 4)
        self.assertEqual(result["neutral_count"], 1)
        self.assertEqual(result["coverage_pct"], 80.0)
        self.assertEqual(result["directional_accuracy_pct"], 75.0)
        self.assertEqual(result["long_hit_rate_pct"], 50.0)
        self.assertEqual(result["short_hit_rate_pct"], 100.0)

    def test_compatibility_action_labels_are_mapped(self):
        data = candles([100, 101, 102, 103])
        result = evaluate_forward_horizon(
            data, horizon_bars=2,
            signal_fn=lambda history: {"signal": "BUY"},
        )
        self.assertEqual(result["observations"][0]["direction"], "LONG")
        self.assertEqual(result["directional_accuracy_pct"], 100.0)

    def test_bearish_market_bias_is_evaluated_without_short_execution_semantics(self):
        data = candles([100, 99, 98, 97])
        result = evaluate_forward_horizon(
            data, horizon_bars=2,
            signal_fn=lambda history: {"direction": "BEARISH"},
        )
        self.assertEqual(result["observations"][0]["direction"], "BEARISH")
        self.assertEqual(result["short_count"], 2)
        self.assertEqual(result["short_hit_rate_pct"], 100.0)

    def test_neutral_band_and_all_neutral(self):
        data = candles([100, 100.01, 100.02, 100.03])
        result = evaluate_forward_horizon(
            data, horizon_bars=2, neutral_band_pct=0.1,
            signal_fn=lambda history: {"direction": "LONG"},
        )
        self.assertEqual(result["long_hit_rate_pct"], 0.0)
        neutral = evaluate_forward_horizon(
            data, horizon_bars=2,
            signal_fn=lambda history: {"direction": "NEUTRAL"},
        )
        self.assertIsNone(neutral["directional_accuracy_pct"])
        self.assertEqual(neutral["coverage_pct"], 0.0)

    def test_invalid_horizon_and_close_are_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_forward_horizon(candles([100, 101]), horizon_bars=0)
        with self.assertRaises(ValueError):
            evaluate_forward_horizon(candles([100, 101]), horizon_bars=2)
        bad = candles([100, 101, 102])
        bad[1]["close"] = float("nan")
        with self.assertRaises(ValueError):
            evaluate_forward_horizon(bad, horizon_bars=1)


if __name__ == "__main__":
    unittest.main()
