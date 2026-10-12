import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from btc_signal_lab.market_data import normalize_klines, save_dataset
from btc_signal_lab.multi_window import evaluate_windows, write_multi_window_report


class MultiWindowEvaluationTests(unittest.TestCase):
    def _dataset(self, root, name, start_hour, interval="1h", count=4):
        step_ms = 3_600_000 if interval == "1h" else 14_400_000
        start_ms = start_hour * 3_600_000
        raw = []
        for index in range(count):
            price = 100.0 + index
            raw.append([
                start_ms + index * step_ms, str(price), str(price + 2),
                str(price - 1), str(price + 1), "10",
            ])
        end_ms = start_ms + count * step_ms
        rows = normalize_klines(raw, start_ms, end_ms, interval)
        start = datetime.fromtimestamp(start_ms / 1000, timezone.utc)
        end = datetime.fromtimestamp(end_ms / 1000, timezone.utc)
        path = Path(root) / f"{name}.csv"
        save_dataset(
            rows, path, symbol="BTCUSDT", interval=interval,
            start=start.isoformat().replace("+00:00", "Z"),
            end=end.isoformat().replace("+00:00", "Z"),
        )
        return {
            "name": name,
            "partition": "train",
            "csv_path": str(path),
            "interval": interval,
            "start_utc": start.isoformat().replace("+00:00", "Z"),
            "end_utc_exclusive": end.isoformat().replace("+00:00", "Z"),
        }

    def test_multi_window_report_contains_all_three_comparators(self):
        with tempfile.TemporaryDirectory() as root:
            first = self._dataset(root, "train", 0)
            second = self._dataset(root, "validation", 10)
            second["partition"] = "validation"
            report = evaluate_windows([first, second], code_commit="abc123")
            self.assertEqual(report["report_schema_version"], "1.0")
            self.assertEqual(len(report["windows"]), 2)
            item = report["windows"][0]
            self.assertEqual(item["flat_cash"]["net_return_pct"], 0.0)
            self.assertEqual(item["flat_cash"]["trade_count"], 0)
            self.assertIn("net_return_pct", item["buy_and_hold"])
            self.assertIn("net_return_pct", item["strategy"])
            self.assertEqual(
                item["forward_horizon_diagnostics"]["classification"],
                "directional diagnostic; not fill-level PnL",
            )

    def test_final_test_must_be_last_and_unique(self):
        with tempfile.TemporaryDirectory() as root:
            first = self._dataset(root, "test", 0)
            first["partition"] = "test"
            second = self._dataset(root, "later", 10)
            with self.assertRaisesRegex(ValueError, "last chronological"):
                evaluate_windows([first, second], code_commit="abc123")
            second["partition"] = "test"
            with self.assertRaisesRegex(ValueError, "at most one"):
                evaluate_windows([first, second], code_commit="abc123")

    def test_overlapping_or_out_of_order_windows_fail(self):
        with tempfile.TemporaryDirectory() as root:
            first = self._dataset(root, "first", 0)
            second = self._dataset(root, "second", 2)
            with self.assertRaisesRegex(ValueError, "chronological"):
                evaluate_windows([first, second], code_commit="abc123")

    def test_manifest_window_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            first = self._dataset(root, "first", 0)
            first["start_utc"] = "1970-01-01T01:00:00Z"
            with self.assertRaisesRegex(ValueError, "start_utc mismatch"):
                evaluate_windows([first], code_commit="abc123")

    def test_same_final_test_period_is_allowed_for_each_timeframe(self):
        with tempfile.TemporaryDirectory() as root:
            hourly = self._dataset(root, "test-1h", 0, interval="1h", count=16)
            four_hour = self._dataset(root, "test-4h", 0, interval="4h", count=4)
            hourly["partition"] = "test"
            four_hour["partition"] = "test"
            report = evaluate_windows([hourly, four_hour], code_commit="abc123")
            self.assertEqual(
                [item["window"]["interval"] for item in report["windows"]],
                ["1h", "4h"],
            )

    def test_identical_inputs_produce_identical_json_bytes(self):
        with tempfile.TemporaryDirectory() as root:
            first = self._dataset(root, "train", 0)
            report_a = evaluate_windows([first], code_commit="abc123")
            report_b = evaluate_windows([first], code_commit="abc123")
            path_a, path_b = Path(root) / "a.json", Path(root) / "b.json"
            write_multi_window_report(report_a, path_a)
            write_multi_window_report(report_b, path_b)
            self.assertEqual(path_a.read_bytes(), path_b.read_bytes())
            self.assertNotIn("evaluation_generated_at_utc", path_a.read_text())

    def test_empty_windows_and_missing_commit_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "at least one"):
            evaluate_windows([], code_commit="abc123")
        with tempfile.TemporaryDirectory() as root:
            first = self._dataset(root, "train", 0)
            with self.assertRaisesRegex(ValueError, "code_commit"):
                evaluate_windows([first], code_commit=" ")


if __name__ == "__main__":
    unittest.main()
