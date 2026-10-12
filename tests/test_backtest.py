import unittest

from btc_signal_lab.backtest import run_backtest


def make_candles(opens, closes=None):
    closes = closes or opens
    return [
        {
            "timestamp": f"t{i}",
            "open": float(o),
            "high": float(max(o, c) + 1),
            "low": float(min(o, c) - 1),
            "close": float(c),
        }
        for i, (o, c) in enumerate(zip(opens, closes))
    ]


class BacktestTests(unittest.TestCase):
    def test_signal_executes_at_next_open_not_same_close(self):
        data = make_candles([100, 110, 120], [105, 115, 125])
        def signal_fn(history):
            return {"signal": "BUY" if len(history) == 1 else "HOLD"}
        result = run_backtest(data, fee_rate=0, slippage_bps=0, signal_fn=signal_fn)
        self.assertEqual(result["trade_count"], 1)
        trade = result["trades"][0]
        self.assertEqual(trade["entry_index"], 1)
        self.assertEqual(trade["entry_price"], 110.0)
        self.assertEqual(trade["exit_index"], 2)
        self.assertEqual(trade["exit_price"], 125.0)

    def test_fees_and_slippage_reduce_result(self):
        data = make_candles([100, 100, 120], [100, 100, 120])
        def signal_fn(history):
            return {"signal": "BUY" if len(history) == 1 else "HOLD"}
        free = run_backtest(data, fee_rate=0, slippage_bps=0, signal_fn=signal_fn)
        costly = run_backtest(data, fee_rate=0.001, slippage_bps=10, signal_fn=signal_fn)
        self.assertGreater(free["final_equity"], costly["final_equity"])

    def test_sell_signal_closes_long_position(self):
        data = make_candles([100, 100, 100, 100], [100, 100, 100, 100])
        def signal_fn(history):
            if len(history) == 1:
                return {"signal": "BUY"}
            if len(history) == 2:
                return {"signal": "SELL"}
            return {"signal": "HOLD"}
        result = run_backtest(data, fee_rate=0, slippage_bps=0, signal_fn=signal_fn)
        self.assertEqual(result["trade_count"], 1)
        self.assertEqual(result["trades"][0]["exit_reason"], "sell_signal")
        self.assertEqual(result["trades"][0]["exit_index"], 2)

    def test_invalid_candles_and_parameters_fail_closed(self):
        with self.assertRaises(ValueError):
            run_backtest([{"open": 1, "high": 1, "low": 1, "close": 1}])
        with self.assertRaises(ValueError):
            run_backtest(make_candles([100, 101]), fee_rate=-0.1)
        with self.assertRaises(ValueError):
            run_backtest(make_candles([100, 101]), initial_capital=0)

    def test_trade_quality_metrics_and_exposure(self):
        data = make_candles([100, 100, 90, 100, 110])
        def signal_fn(history):
            if len(history) == 1:
                return {"signal": "BUY"}
            if len(history) == 2:
                return {"signal": "SELL"}
            if len(history) == 3:
                return {"signal": "BUY"}
            return {"signal": "HOLD"}

        result = run_backtest(data, fee_rate=0, slippage_bps=0, signal_fn=signal_fn)
        self.assertEqual(result["trade_count"], 2)
        self.assertAlmostEqual(result["gross_profit"], 900.0)
        self.assertAlmostEqual(result["gross_loss"], 1000.0)
        self.assertAlmostEqual(result["profit_factor"], 0.9)
        self.assertAlmostEqual(result["average_holding_bars"], 1.0)
        self.assertAlmostEqual(result["exposure_pct"], 60.0)
        self.assertAlmostEqual(result["average_trade_pnl"], -50.0)
        self.assertAlmostEqual(result["trades"][0]["net_return_pct"], -10.0)

    def test_profit_factor_is_null_when_no_losing_trades(self):
        data = make_candles([100, 100, 110])
        result = run_backtest(
            data, fee_rate=0, slippage_bps=0,
            signal_fn=lambda history: {"signal": "BUY" if len(history) == 1 else "HOLD"},
        )
        self.assertIsNone(result["profit_factor"])
        self.assertGreater(result["gross_profit"], 0)
        self.assertEqual(result["gross_loss"], 0.0)

    def test_empty_signals_keep_capital_and_report_zero_trades(self):
        result = run_backtest(make_candles([100, 101, 102]), fee_rate=0, slippage_bps=0,
                              signal_fn=lambda history: {"signal": "HOLD"})
        self.assertEqual(result["trade_count"], 0)
        self.assertEqual(result["final_equity"], 10000.0)
        self.assertEqual(result["net_return_pct"], 0.0)
        self.assertEqual(result["gross_profit"], 0.0)
        self.assertEqual(result["gross_loss"], 0.0)
        self.assertIsNone(result["profit_factor"])
        self.assertEqual(result["exposure_pct"], 0.0)


if __name__ == "__main__":
    unittest.main()
