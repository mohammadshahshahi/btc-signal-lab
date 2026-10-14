import tempfile
import unittest
from pathlib import Path

from btc_signal_lab.market_data import normalize_klines, parse_utc, save_dataset


class MarketDataTests(unittest.TestCase):
    def test_parse_utc_requires_timezone(self):
        with self.assertRaises(ValueError):
            parse_utc("2026-01-01T00:00:00")
        self.assertEqual(parse_utc("2026-01-01T03:30:00+03:30").isoformat(),
                         "2026-01-01T00:00:00+00:00")

    def test_normalize_valid_rows_and_filter_range(self):
        rows = [
            [0, "100", "102", "99", "101", "10"],
            [3_600_000, "101", "103", "100", "102", "11"],
            [7_200_000, "102", "104", "101", "103", "12"],
        ]
        result = normalize_klines(rows, 3_600_000, 10_800_000, "1h")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["timestamp_ms"], 3_600_000)
        self.assertEqual(result[1]["close"], 103.0)

    def test_normalize_rejects_gap_duplicate_and_bad_ohlc(self):
        with self.assertRaises(ValueError):
            normalize_klines([[0, "100", "102", "99", "101", "1"],
                              [7_200_000, "101", "103", "100", "102", "1"]],
                             0, 10_800_000, "1h")
        with self.assertRaises(ValueError):
            normalize_klines([[0, "100", "102", "99", "101", "1"],
                              [0, "100", "102", "99", "101", "1"]],
                             0, 3_600_000, "1h")
        with self.assertRaises(ValueError):
            normalize_klines([[0, "100", "98", "99", "101", "1"]],
                             0, 3_600_000, "1h")

    def test_save_writes_manifest_and_hash(self):
        rows = normalize_klines([[0, "100", "102", "99", "101", "10"]],
                                0, 3_600_000, "1h")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "btc.csv"
            manifest = save_dataset(rows, path, symbol="BTCUSDT", interval="1h",
                                    start="1970-01-01T00:00:00Z",
                                    end="1970-01-01T01:00:00Z")
            self.assertEqual(manifest["row_count"], 1)
            self.assertEqual(len(manifest["csv_sha256"]), 64)
            self.assertTrue(path.with_suffix(".csv.manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
