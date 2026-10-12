import unittest

from btc_signal_lab.paper_trading import PaperTrader


class PaperTraderTests(unittest.TestCase):
    def test_buy_sell_records_net_trade_and_fees(self):
        trader = PaperTrader(initial_cash=10_000, fee_rate=0.001, slippage_bps=0)
        opened = trader.execute("BUY", 100, "2026-10-12T10:00:00Z")
        self.assertEqual(opened["action"], "OPEN_LONG")
        self.assertEqual(trader.cash, 0)
        closed = trader.execute("SELL", 110, "2026-10-12T11:00:00Z")
        self.assertEqual(closed["action"], "CLOSE_LONG")
        self.assertEqual(len(trader.trades), 1)
        self.assertGreater(trader.trades[0]["net_pnl"], 0)
        self.assertEqual(trader.snapshot(110)["live_orders_submitted"], 0)

    def test_hold_and_duplicate_entry_are_safe(self):
        trader = PaperTrader()
        self.assertEqual(trader.execute("HOLD", 100, "2026-10-12T10:00:00Z")["action"], "HOLD")
        trader.execute("BUY", 100, "2026-10-12T11:00:00Z")
        self.assertEqual(trader.execute("BUY", 105, "2026-10-12T12:00:00Z")["action"], "HOLD")
        self.assertEqual(len(trader.events), 3)
        self.assertEqual(len(trader.trades), 0)

    def test_sell_while_flat_does_not_open_short(self):
        trader = PaperTrader()
        event = trader.execute("SELL", 100, "2026-10-12T10:00:00Z")
        self.assertEqual(event["action"], "HOLD")
        self.assertEqual(trader.quantity, 0)

    def test_fees_and_slippage_reduce_equity(self):
        free = PaperTrader(fee_rate=0, slippage_bps=0)
        costly = PaperTrader(fee_rate=0.001, slippage_bps=10)
        for trader in (free, costly):
            trader.execute("BUY", 100, "2026-10-12T10:00:00Z")
        self.assertLess(costly.equity(110), free.equity(110))

    def test_invalid_parameters_and_inputs_are_rejected(self):
        with self.assertRaises(ValueError):
            PaperTrader(initial_cash=0)
        trader = PaperTrader()
        with self.assertRaises(ValueError):
            trader.execute("BUY", float("nan"), "2026-10-12T10:00:00Z")
        with self.assertRaises(ValueError):
            trader.execute("BUY", 100, "2026-10-12T10:00:00")

    def test_equity_while_flat_equals_cash(self):
        trader = PaperTrader(initial_cash=2500)
        self.assertEqual(trader.equity(100), 2500)


if __name__ == "__main__":
    unittest.main()
