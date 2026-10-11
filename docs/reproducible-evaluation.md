# Reproducible Evaluation Pipeline

After downloading a complete, contiguous public candle range using
`market_data.download_binance_klines` and saving it with `save_dataset`, verify
the CSV against its manifest and run the signal strategy with:

```python
from btc_signal_lab.evaluation import evaluate_dataset, write_report

report = evaluate_dataset(
    "data/btcusdt_1h_2025-01.csv",
    initial_capital=10_000,
    fee_rate=0.001,       # 0.1% per side; confirm the venue's actual fee tier
    slippage_bps=5,       # 0.05% per side; a scenario assumption, not observed spread
)
write_report(report, "reports/btcusdt_1h_2025-01.json")
print(report["results"])
```

The evaluator fails closed if the adjacent manifest is missing, the file hash
changes, row count/range disagrees, or timestamps are duplicate, unordered, or
missing. The report records dataset hash, source, date range, row count, strategy,
execution timing, and cost assumptions.

**Important:** this pipeline makes a backtest reproducible; it does not establish
statistical significance or out-of-sample robustness. Freeze strategy parameters
before examining a held-out period, account for costs, and do not interpret the
baseline's historical return as a forecast.
