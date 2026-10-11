# Reproducible Evaluation Pipeline

After using `market_data.download_binance_klines` and `save_dataset`, verify
the saved CSV against its adjacent manifest and run:

```python
from btc_signal_lab.evaluation import evaluate_dataset, write_report
report = evaluate_dataset("data/btcusdt_1h_2025-01.csv",
                          initial_capital=10000, fee_rate=0.001,
                          slippage_bps=5)
write_report(report, "reports/btcusdt_1h_2025-01.json")
print(report["results"])
```

Evaluation fails closed when the manifest is missing, the CSV hash or row count
does not match, or the date range/timestamp cadence is inconsistent. The report
records the dataset hash, source, range, strategy, execution timing, and costs.

This improves reproducibility but does not establish future profitability.
Freeze parameters before evaluating held-out data. The fee and slippage inputs
are assumptions and must be checked against the venue and market conditions.
