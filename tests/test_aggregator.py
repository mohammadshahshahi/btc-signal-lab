import unittest

from btc_signal_lab.aggregator import aggregate_signals


def rows(labels):
    return [
        {"timestamp": f"2026-10-12T{hour:02d}:00:00Z", "signal": label}
        for hour, label in enumerate(labels)
    ]


class AggregatorTests(unittest.TestCase):
    def test_single_signal_is_renormalized(self):
        result = aggregate_signals(rows(["BUY"]))
        self.assertEqual(result["score"], 100.0)
        self.assertEqual(result["signal"], "BUY")
        self.assertEqual(result["sample_count"], 1)

    def test_newest_signal_has_highest_weight(self):
        result = aggregate_signals(rows(["SELL", "SELL", "SELL", "SELL", "BUY"]))
        self.assertAlmostEqual(result["score"], 40.0)
        self.assertEqual(result["signal"], "HOLD")

    def test_five_buy_signals_produce_buy(self):
        result = aggregate_signals(rows(["BUY"] * 5))
        self.assertEqual(result["score"], 100.0)
        self.assertEqual(result["signal"], "BUY")
        self.assertEqual(result["horizon"], "24h")
        self.assertEqual(result["direction"], "LONG")

    def test_numeric_scores_are_supported(self):
        data = [
            {"timestamp": f"2026-10-12T{hour:02d}:00:00Z", "score": 80}
            for hour in range(3)
        ]
        self.assertEqual(aggregate_signals(data)["signal"], "BUY")

    def test_only_five_most_recent_are_used(self):
        data = rows(["SELL"] * 5 + ["BUY"] * 5)
        result = aggregate_signals(data)
        self.assertEqual(result["sample_count"], 5)
        self.assertEqual(result["signal"], "BUY")

    def test_invalid_and_duplicate_timestamps_are_rejected(self):
        with self.assertRaises(ValueError):
            aggregate_signals([{"timestamp": "2026-10-12T10:00:00", "signal": "BUY"}])
        duplicate = rows(["BUY", "SELL"])
        duplicate[1]["timestamp"] = duplicate[0]["timestamp"]
        with self.assertRaises(ValueError):
            aggregate_signals(duplicate)

    def test_unknown_signal_and_out_of_range_score_are_rejected(self):
        with self.assertRaises(ValueError):
            aggregate_signals([{"timestamp": "2026-10-12T10:00:00Z", "signal": "LONG"}])
        with self.assertRaises(ValueError):
            aggregate_signals([{"timestamp": "2026-10-12T10:00:00Z", "score": 101}])


if __name__ == "__main__":
    unittest.main()
