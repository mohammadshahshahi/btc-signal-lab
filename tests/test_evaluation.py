import tempfile
import unittest
from pathlib import Path
from btc_signal_lab.evaluation import evaluate_dataset, load_verified_dataset
from btc_signal_lab.market_data import normalize_klines, save_dataset

class EvaluationTests(unittest.TestCase):
    def make_data(self, directory):
        rows=normalize_klines([[0,"100","102","99","101","10"],
          [3600000,"101","103","100","102","11"],
          [7200000,"102","104","101","103","12"]],0,10800000,"1h")
        path=Path(directory)/"candles.csv"
        save_dataset(rows,path,symbol="BTCUSDT",interval="1h",
          start="1970-01-01T00:00:00Z",end="1970-01-01T03:00:00Z")
        return path
    def test_verified_data_and_report(self):
        with tempfile.TemporaryDirectory() as d:
            path=self.make_data(d); rows,manifest=load_verified_dataset(path)
            self.assertEqual(len(rows),3)
            report=evaluate_dataset(path,fee_rate=0,slippage_bps=0)
            self.assertEqual(report["dataset"]["csv_sha256"],manifest["csv_sha256"])
            self.assertEqual(report["results"]["trade_count"],0)
            self.assertIsNone(report["forward_horizon"])
            self.assertTrue(report["evaluation_generated_at_utc"].endswith("Z"))
    def test_tampered_file_fails_hash(self):
        with tempfile.TemporaryDirectory() as d:
            path=self.make_data(d); path.write_text(path.read_text()+"\n")
            with self.assertRaisesRegex(ValueError,"SHA-256"): load_verified_dataset(path)
    def test_missing_manifest_fails(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"x.csv"; path.write_text("timestamp,open,high,low,close,volume\n")
            with self.assertRaises(FileNotFoundError): load_verified_dataset(path)

if __name__=="__main__": unittest.main()
