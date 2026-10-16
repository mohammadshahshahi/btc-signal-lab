import csv
import io
import json
import zipfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from btc_signal_lab.market_data import (
    BINANCE_ARCHIVE_SOURCE, _download_from_binance_archive, _download_from_kucoin,
    normalize_klines, parse_utc, save_dataset,
)


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

    def test_normalize_rejects_out_of_order_payload_without_sorting(self):
        rows = [
            [3_600_000, "101", "103", "100", "102", "1"],
            [0, "100", "102", "99", "101", "1"],
        ]
        with self.assertRaisesRegex(ValueError, "out-of-order"):
            normalize_klines(rows, 0, 7_200_000, "1h")

    def test_normalize_rejects_duplicate_timestamp_in_source_order(self):
        rows = [
            [0, "100", "102", "99", "101", "1"],
            [0, "100", "102", "99", "101", "1"],
        ]
        with self.assertRaisesRegex(ValueError, "duplicate"):
            normalize_klines(rows, 0, 3_600_000, "1h")

    def test_kucoin_newest_first_response_is_normalized_chronologically(self):
        # KuCoin returns candle rows newest-first; the provider adapter must
        # normalize that documented order before the strict shared validator.
        payload = {
            "code": "200000",
            "data": [
                ["7200", "102", "103", "104", "101", "12", "1236"],
                ["3600", "101", "102", "103", "100", "11", "1122"],
                ["0", "100", "101", "102", "99", "10", "1010"],
            ],
        }
        with patch("btc_signal_lab.market_data.urlopen") as mocked_urlopen:
            mocked_urlopen.return_value.__enter__.return_value.read.return_value = (
                json.dumps(payload).encode("utf-8")
            )
            rows = _download_from_kucoin(
                "BTCUSDT", "1h", 0, 10_800_000, timeout=1.0
            )

        self.assertEqual(
            [row["timestamp_ms"] for row in rows],
            [0, 3_600_000, 7_200_000],
        )
        self.assertEqual([row["open"] for row in rows], [100.0, 101.0, 102.0])

    def test_binance_archive_zip_is_parsed_and_strictly_validated(self):
        # Build a deterministic monthly archive fixture; no live network needed.
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        writer.writerow(["open_time", "open", "high", "low", "close", "volume"])
        writer.writerow([0, "100", "102", "99", "101", "10"])
        writer.writerow([3_600_000, "101", "103", "100", "102", "11"])
        writer.writerow([7_200_000, "102", "104", "101", "103", "12"])
        archive_buffer = io.BytesIO()
        with zipfile.ZipFile(archive_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("BTCUSDT-1h-1970-01.csv", csv_buffer.getvalue())
        archive_bytes = archive_buffer.getvalue()

        with patch("btc_signal_lab.market_data.urlopen") as mocked_urlopen:
            mocked_urlopen.return_value.__enter__.return_value.read.return_value = archive_bytes
            rows = _download_from_binance_archive(
                "BTCUSDT", "1h", 0, 10_800_000, timeout=1.0
            )

        self.assertEqual([row["timestamp_ms"] for row in rows], [0, 3_600_000, 7_200_000])
        self.assertEqual([row["close"] for row in rows], [101.0, 102.0, 103.0])
        requested_url = mocked_urlopen.call_args.args[0].full_url
        self.assertEqual(
            requested_url,
            f"{BINANCE_ARCHIVE_SOURCE}/BTCUSDT/1h/BTCUSDT-1h-1970-01.zip",
        )

    def test_binance_archive_gap_is_rejected_not_filled(self):
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        writer.writerow(["open_time", "open", "high", "low", "close", "volume"])
        writer.writerow([0, "100", "102", "99", "101", "10"])
        writer.writerow([7_200_000, "102", "104", "101", "103", "12"])
        archive_buffer = io.BytesIO()
        with zipfile.ZipFile(archive_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("BTCUSDT-1h-1970-01.csv", csv_buffer.getvalue())

        with patch("btc_signal_lab.market_data.urlopen") as mocked_urlopen:
            mocked_urlopen.return_value.__enter__.return_value.read.return_value = archive_buffer.getvalue()
            with self.assertRaisesRegex(ValueError, "candle gap"):
                _download_from_binance_archive(
                    "BTCUSDT", "1h", 0, 10_800_000, timeout=1.0
                )

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
