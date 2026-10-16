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
    aggregate_minute_klines, download_binance_1m_archive_aggregate,
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


    @staticmethod
    def _minute_fixture(count=60):
        rows = []
        for index in range(count):
            opened = 100.0 + index / 100
            rows.append([
                index * 60_000, str(opened), str(opened + 1),
                str(opened - 1), str(opened + 0.5), "1",
            ])
        return rows

    def test_aggregate_exact_1h_from_60_consecutive_minutes(self):
        rows, provenance = aggregate_minute_klines(
            self._minute_fixture(), 0, 3_600_000, "1h"
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["timestamp_ms"], 0)
        self.assertEqual(rows[0]["open"], 100.0)
        self.assertAlmostEqual(rows[0]["high"], 101.59)
        self.assertEqual(rows[0]["low"], 99.0)
        self.assertAlmostEqual(rows[0]["close"], 101.09)
        self.assertEqual(rows[0]["volume"], 60.0)
        self.assertEqual(provenance["expected_constituents_per_bucket"], 60)
        self.assertEqual(provenance["actual_constituent_counts"]["minimum"], 60)
        self.assertEqual(provenance["actual_constituent_counts"]["maximum"], 60)

    def test_aggregate_rejects_single_missing_minute(self):
        rows = self._minute_fixture()
        del rows[30]
        with self.assertRaisesRegex(ValueError, "gap"):
            aggregate_minute_klines(rows, 0, 3_600_000, "1h")

    def test_aggregate_rejects_duplicate_minute(self):
        rows = self._minute_fixture()
        rows.insert(20, rows[19])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            aggregate_minute_klines(rows, 0, 3_600_000, "1h")

    def test_aggregate_rejects_out_of_order_minute(self):
        rows = self._minute_fixture()
        rows[10], rows[11] = rows[11], rows[10]
        with self.assertRaisesRegex(ValueError, "out-of-order"):
            aggregate_minute_klines(rows, 0, 3_600_000, "1h")

    def test_aggregate_rejects_invalid_ohlcv_minute(self):
        rows = self._minute_fixture()
        rows[17][2] = "1"  # high below the row's open and low
        with self.assertRaisesRegex(ValueError, "inconsistent OHLC"):
            aggregate_minute_klines(rows, 0, 3_600_000, "1h")

    def test_aggregate_rejects_incomplete_final_bucket(self):
        rows = self._minute_fixture(59)
        with self.assertRaisesRegex(ValueError, "align to complete UTC"):
            aggregate_minute_klines(rows, 0, 3_540_000, "1h")


    def test_aggregate_enforces_4h_and_1d_constituent_counts(self):
        four_hour, four_hour_meta = aggregate_minute_klines(
            self._minute_fixture(240), 0, 14_400_000, "4h"
        )
        daily, daily_meta = aggregate_minute_klines(
            self._minute_fixture(1440), 0, 86_400_000, "1d"
        )
        self.assertEqual(len(four_hour), 1)
        self.assertEqual(four_hour_meta["expected_constituents_per_bucket"], 240)
        self.assertEqual(len(daily), 1)
        self.assertEqual(daily_meta["expected_constituents_per_bucket"], 1440)

    def test_failed_1m_archive_validation_reports_url_and_sha256(self):
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        writer.writerow(["open_time", "open", "high", "low", "close", "volume"])
        writer.writerows(self._minute_fixture(59))
        archive_buffer = io.BytesIO()
        with zipfile.ZipFile(archive_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("BTCUSDT-1m-1970-01.csv", csv_buffer.getvalue())
        archive_bytes = archive_buffer.getvalue()

        with patch("btc_signal_lab.market_data.urlopen") as mocked_urlopen:
            mocked_urlopen.return_value.__enter__.return_value.read.return_value = archive_bytes
            with self.assertRaisesRegex(ValueError, "archive_evidence") as raised:
                download_binance_1m_archive_aggregate(
                    "BTCUSDT", "1h", "1970-01-01T00:00:00Z",
                    "1970-01-01T01:00:00Z", timeout=1.0,
                )

        message = str(raised.exception)
        self.assertIn("BTCUSDT-1m-1970-01.zip", message)
        self.assertIn("sha256", message)
        self.assertIn("incomplete 1m source range", message)


    def test_daily_archive_repairs_monthly_gap_from_same_venue(self):
        def make_archive(rows, member_name):
            csv_buffer = io.StringIO()
            writer = csv.writer(csv_buffer)
            writer.writerow(["open_time", "open", "high", "low", "close", "volume"])
            writer.writerows(rows)
            archive_buffer = io.BytesIO()
            with zipfile.ZipFile(archive_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr(member_name, csv_buffer.getvalue())
            return archive_buffer.getvalue()

        monthly_bytes = make_archive(self._minute_fixture(59), "BTCUSDT-1m-1970-01.csv")
        daily_bytes = make_archive(self._minute_fixture(60), "BTCUSDT-1m-1970-01-01.csv")

        def response(payload):
            mocked_response = unittest.mock.MagicMock()
            mocked_response.__enter__.return_value.read.return_value = payload
            return mocked_response

        with patch(
            "btc_signal_lab.market_data.urlopen",
            side_effect=[response(monthly_bytes), response(daily_bytes)],
        ) as mocked_urlopen:
            rows, provenance = download_binance_1m_archive_aggregate(
                "BTCUSDT", "1h", "1970-01-01T00:00:00Z",
                "1970-01-01T01:00:00Z", timeout=1.0,
            )

        self.assertEqual(len(rows), 1)
        self.assertEqual(provenance["daily_replacement_dates"], ["1970-01-01"])
        self.assertEqual(len(provenance["source_archive_sha256"]), 2)
        requested_urls = [call.args[0].full_url for call in mocked_urlopen.call_args_list]
        self.assertTrue(any("/monthly/" in url for url in requested_urls))
        self.assertTrue(any("/daily/" in url for url in requested_urls))


    def test_daily_replacement_preserves_day_order_when_monthly_has_late_rows(self):
        def make_archive(rows, member_name):
            csv_buffer = io.StringIO()
            writer = csv.writer(csv_buffer)
            writer.writerow(["open_time", "open", "high", "low", "close", "volume"])
            writer.writerows(rows)
            archive_buffer = io.BytesIO()
            with zipfile.ZipFile(archive_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr(member_name, csv_buffer.getvalue())
            return archive_buffer.getvalue()

        monthly_rows = self._minute_fixture(1440)
        del monthly_rows[30]  # Internal gap; later rows, including 23:59, remain present.
        monthly_bytes = make_archive(monthly_rows, "BTCUSDT-1m-1970-01.csv")
        daily_bytes = make_archive(
            self._minute_fixture(1440), "BTCUSDT-1m-1970-01-01.csv"
        )

        def response(payload):
            mocked_response = unittest.mock.MagicMock()
            mocked_response.__enter__.return_value.read.return_value = payload
            return mocked_response

        with patch(
            "btc_signal_lab.market_data.urlopen",
            side_effect=[response(monthly_bytes), response(daily_bytes)],
        ):
            rows, provenance = download_binance_1m_archive_aggregate(
                "BTCUSDT", "1d", "1970-01-01T00:00:00Z",
                "1970-01-02T00:00:00Z", timeout=1.0,
            )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["timestamp_ms"], 0)
        self.assertEqual(provenance["daily_replacement_dates"], ["1970-01-01"])
        self.assertEqual(len(provenance["source_archive_sha256"]), 2)


    def test_daily_archive_out_of_order_is_rejected_with_source_evidence(self):
        def make_archive(rows, member_name):
            csv_buffer = io.StringIO()
            writer = csv.writer(csv_buffer)
            writer.writerow(["open_time", "open", "high", "low", "close", "volume"])
            writer.writerows(rows)
            archive_buffer = io.BytesIO()
            with zipfile.ZipFile(archive_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr(member_name, csv_buffer.getvalue())
            return archive_buffer.getvalue()

        monthly_bytes = make_archive(self._minute_fixture(59), "BTCUSDT-1m-1970-01.csv")
        daily_rows = self._minute_fixture(60)
        daily_rows.append(daily_rows.pop(0))  # Simulate a source archive ordering defect.
        daily_bytes = make_archive(daily_rows, "BTCUSDT-1m-1970-01-01.csv")

        def response(payload):
            mocked_response = unittest.mock.MagicMock()
            mocked_response.__enter__.return_value.read.return_value = payload
            return mocked_response

        with patch(
            "btc_signal_lab.market_data.urlopen",
            side_effect=[response(monthly_bytes), response(daily_bytes)],
        ):
            with self.assertRaisesRegex(ValueError, "daily same-venue fallback failed") as raised:
                download_binance_1m_archive_aggregate(
                    "BTCUSDT", "1h", "1970-01-01T00:00:00Z",
                    "1970-01-01T01:00:00Z", timeout=1.0,
                )

        message = str(raised.exception)
        self.assertIn("daily archive is not strictly ordered", message)
        self.assertIn("archive_evidence", message)
        self.assertIn("BTCUSDT-1m-1970-01-01.zip", message)


    def test_download_1m_archive_records_archive_provenance(self):
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        writer.writerow(["open_time", "open", "high", "low", "close", "volume"])
        writer.writerows(self._minute_fixture())
        archive_buffer = io.BytesIO()
        with zipfile.ZipFile(archive_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("BTCUSDT-1m-1970-01.csv", csv_buffer.getvalue())
        archive_bytes = archive_buffer.getvalue()

        with patch("btc_signal_lab.market_data.urlopen") as mocked_urlopen:
            mocked_urlopen.return_value.__enter__.return_value.read.return_value = archive_bytes
            rows, provenance = download_binance_1m_archive_aggregate(
                "BTCUSDT", "1h", "1970-01-01T00:00:00Z",
                "1970-01-01T01:00:00Z", timeout=1.0,
            )
        self.assertEqual(len(rows), 1)
        self.assertEqual(provenance["source_interval"], "1m")
        self.assertEqual(provenance["target_interval"], "1h")
        self.assertEqual(provenance["source_archive_urls"], [
            f"{BINANCE_ARCHIVE_SOURCE}/BTCUSDT/1m/BTCUSDT-1m-1970-01.zip"
        ])
        self.assertEqual(len(provenance["source_archive_sha256"][0]["sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
