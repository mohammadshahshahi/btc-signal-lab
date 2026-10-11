import unittest

from btc_signal_lab.benchmark import run_buy_and_hold


def candles(opens, closes=None):
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


class BuyAndHoldTests(unittest.TestCase):
    def test_flat_market_loses_only_modeled_costs(self):
        result = run_buy_and_hold(candles([100, 100, 100], [100, 100, 100]),
                                  fee_rate=0, slippage_bps=0)
        self.assertAlmostEqual(result["final_equity"], 10000.0)
        self.assertAlmostEqual(result["net_return_pct"], 0.0)
        self.assertEqual(result["entry_index"], 1)
        self.assertEqual(result["exit_index"], 2)

    def test_up_market_gains_before_costs(self):
        result = run_buy_and_hold(candles([100, 100, 120], [100, 110, 130]),
                                  fee_rate=0, slippage_bps=0)
        self.assertAlmostEqual(result["final_equity"], 10000 * 130 / 100)
        self.assertGreater(result["net_return_pct"], 0)

    def test_fees_and_slippage_reduce_result(self):
        data = candles([100, 100, 120], [100, 110, 130])
        free = run_buy_and_hold(data, fee_rate=0, slippage_bps=0)
        costly = run_buy_and_hold(data, fee_rate=0.001, slippage_bps=10)
        self.assertGreater(free["final_equity"], costly["final_equity"])

    def test_invalid_parameters_rejected(self):
        with self.assertRaises(ValueError):
            run_buy_and_hold(candles([100, 100]), fee_rate=-0.1)
        with self.assertRaises(ValueError):
            run_buy_and_hold(candles([100, 100]), initial_capital=0)


if __name__ == "__main__":
    unittest.main()
