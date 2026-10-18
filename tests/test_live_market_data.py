import json
import unittest
from unittest.mock import patch

from btc_signal_lab.live_market_data import fetch_latest_closed_klines


class LiveMarketDataTests(unittest.TestCase):
    @staticmethod
    def _payload(count=121, step=3_600_000, *, missing_index=None):
        rows = []
        for index in range(count):
            if index == missing_index:
                continue
            price = 100.0 + index
            rows.append([
                index * step, str(price), str(price + 2), str(price - 2),
                str(price + 1), "10", (index + 1) * step - 1,
                "1000", 1, "5", "500", "0",
            ])
        return rows

    def _mock_response(self, payload):
        return patch(
            "btc_signal_lab.live_market_data.urlopen",
            **{"return_value.__enter__.return_value.read.return_value": json.dumps(payload).encode("utf-8")},
        )

    def test_returns_only_closed_contiguous_candles_with_provenance(self):
        step = 3_600_000
        now_ms = 120 * step + 30_000
        with self._mock_response(self._payload()) as mocked:
            rows, provenance = fetch_latest_closed_klines(
                "BTCUSDT", "1h", limit=121, now_ms=now_ms
            )
        self.assertEqual(len(rows), 120)
        self.assertEqual(rows[-1]["timestamp_ms"], 119 * step)
        self.assertEqual(provenance["closed_candle_count"], 120)
        self.assertEqual(provenance["staleness_ms"], 30_000)
        self.assertEqual(len(provenance["response_sha256"]), 64)
        self.assertEqual(provenance["live_orders_submitted"], 0)
        self.assertEqual(mocked.call_count, 1)

    def test_supports_15m_interval_used_by_workflow(self):
        step = 900_000
        now_ms = 120 * step + 30_000
        with self._mock_response(self._payload(step=step)) as _:
            rows, provenance = fetch_latest_closed_klines(
                "BTCUSDT", "15m", limit=121, now_ms=now_ms
            )
        self.assertEqual(len(rows), 120)
        self.assertEqual(provenance["interval"], "15m")
        self.assertEqual(rows[-1]["timestamp_ms"], 119 * step)

    def test_rejects_gap_in_live_payload(self):
        step = 3_600_000
        with self._mock_response(self._payload(missing_index=60)) as _:
            with self.assertRaisesRegex(ValueError, "gap"):
                fetch_latest_closed_klines(
                    "BTCUSDT", "1h", limit=120, now_ms=120 * step + 30_000
                )

    def test_rejects_out_of_order_provider_rows_before_normalization(self):
        step = 3_600_000
        payload = self._payload()
        payload[60], payload[61] = payload[61], payload[60]
        with self._mock_response(payload) as _:
            with self.assertRaisesRegex(ValueError, "strictly increasing"):
                fetch_latest_closed_klines(
                    "BTCUSDT", "1h", limit=121, now_ms=120 * step + 30_000
                )

    def test_rejects_misaligned_provider_timestamps(self):
        step = 3_600_000
        payload = self._payload()
        for row in payload:
            row[0] += 1_000
        with self._mock_response(payload) as _:
            with self.assertRaisesRegex(ValueError, "not aligned"):
                fetch_latest_closed_klines(
                    "BTCUSDT", "1h", limit=121, now_ms=120 * step + 30_000
                )

    def test_rejects_stale_latest_closed_candle(self):
        step = 3_600_000
        with self._mock_response(self._payload()) as _:
            with self.assertRaisesRegex(ValueError, "stale"):
                fetch_latest_closed_klines(
                    "BTCUSDT", "1h", limit=121, now_ms=125 * step
                )

    def test_rejects_insufficient_history(self):
        step = 3_600_000
        with self._mock_response(self._payload(count=30)) as _:
            with self.assertRaisesRegex(ValueError, "insufficient closed candles"):
                fetch_latest_closed_klines(
                    "BTCUSDT", "1h", limit=51, now_ms=31 * step + 30_000
                )

    def test_rejects_bad_limit(self):
        with self.assertRaisesRegex(ValueError, "limit"):
            fetch_latest_closed_klines(limit=20, now_ms=10_000_000)


if __name__ == "__main__":
    unittest.main()
