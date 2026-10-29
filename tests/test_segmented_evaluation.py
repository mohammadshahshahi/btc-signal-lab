import unittest

from btc_signal_lab.segmented_evaluation import (
    evaluate_contiguous_segments,
    split_contiguous_segments,
)


def candles(timestamps):
    return [
        {
            "timestamp_ms": ts,
            "timestamp": f"ts-{ts}",
            "open": 100.0 + i,
            "high": 102.0 + i,
            "low": 99.0 + i,
            "close": 101.0 + i,
            "volume": 10.0,
        }
        for i, ts in enumerate(timestamps)
    ]


TEST_OUTAGE = {
    "event_id": "test-documented-outage",
    "venue": "Binance",
    "market": "Spot",
    "symbol_scope": "all_spot_symbols",
    "documented_suspension_start_utc": "1970-01-01T00:00:00Z",
    "documented_resume_utc": "1970-01-01T00:40:00Z",
    "sources": [{"url": "https://example.com/test-outage-evidence"}],
}


def evaluate(data, **kwargs):
    return evaluate_contiguous_segments(
        data, interval_ms=60_000, venue="Binance", market="Spot",
        symbol="BTCUSDT", outage_events=[TEST_OUTAGE], **kwargs,
    )


class SegmentedEvaluationTests(unittest.TestCase):
    def test_splits_at_gaps_without_synthesizing_rows(self):
        data = candles([0, 60_000, 120_000, 300_000, 360_000])
        segments = split_contiguous_segments(data, interval_ms=60_000)
        self.assertEqual([len(segment) for segment in segments], [3, 2])
        self.assertEqual(sum(map(len, segments)), len(data))
        self.assertEqual(
            [item["timestamp_ms"] for segment in segments for item in segment],
            [0, 60_000, 120_000, 300_000, 360_000],
        )

    def test_duplicate_and_out_of_order_timestamps_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            split_contiguous_segments(candles([0, 60_000, 60_000]), interval_ms=60_000)
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            split_contiguous_segments(candles([0, 120_000, 60_000]), interval_ms=60_000)

    def test_non_integer_timestamps_and_invalid_interval_rejected(self):
        data = candles([0, 60_000])
        data[1]["timestamp_ms"] = "60000"
        with self.assertRaisesRegex(ValueError, "integer epoch"):
            split_contiguous_segments(data, interval_ms=60_000)
        with self.assertRaises(ValueError):
            split_contiguous_segments(candles([0]), interval_ms=0)

    def test_unexplained_gaps_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "unexplained or unapproved data gap"):
            evaluate_contiguous_segments(
                candles([0, 60_000, 180_000]), interval_ms=60_000,
                venue="Binance", market="Spot", symbol="BTCUSDT",
                outage_events=[],
            )

    def test_backtest_and_forward_horizon_are_segment_local(self):
        # The 25-candle first segment can produce a 24-bar forward label;
        # the two-candle second segment cannot borrow future candles.
        first = [i * 60_000 for i in range(25)]
        second = [2_000_000 + i * 60_000 for i in range(2)]
        result = evaluate(
            candles(first + second), horizon_bars=24, fee_rate=0, slippage_bps=0
        )
        self.assertEqual(result["segment_count"], 2)
        self.assertEqual(result["total_candles"], 27)
        self.assertIsNotNone(result["segments"][0]["forward_horizon"])
        self.assertEqual(
            result["segments"][0]["forward_horizon"]["observation_count"], 1
        )
        self.assertIsNone(result["segments"][1]["forward_horizon"])
        self.assertEqual(result["segments"][1]["candle_count"], 2)
        self.assertEqual(
            result["outage_policy"]["matched_event_ids"], ["test-documented-outage"]
        )
        self.assertFalse(result["policy"]["synthetic_candles"])
        self.assertFalse(result["policy"]["indicator_history_crosses_gap"])
        self.assertFalse(result["policy"]["positions_cross_gaps"])
        self.assertFalse(result["policy"]["forward_labels_cross_gaps"])

    def test_manifest_lists_only_events_that_matched_observed_gaps(self):
        unrelated = {
            **TEST_OUTAGE,
            "event_id": "unused-unrelated-event",
            "symbol_scope": "ETHUSDT",
        }
        data = candles([0, 60_000, 120_000, 300_000, 360_000])
        result = evaluate_contiguous_segments(
            data, interval_ms=60_000, venue="Binance", market="Spot",
            symbol="BTCUSDT", outage_events=[TEST_OUTAGE, unrelated],
            horizon_bars=24,
        )
        self.assertEqual(
            result["outage_policy"]["matched_event_ids"],
            ["test-documented-outage"],
        )

    def test_single_candle_segment_is_ineligible_for_backtest(self):
        result = evaluate(candles([0, 120_000, 240_000]), horizon_bars=24)
        self.assertEqual(result["segment_count"], 3)
        self.assertTrue(all(
            item["eligibility"] == "ineligible_too_short_for_backtest"
            for item in result["segments"]
        ))
        self.assertTrue(all(item["backtest"] is None for item in result["segments"]))


if __name__ == "__main__":
    unittest.main()
