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

## Baseline comparison

Report schema 1.1 includes both the Signal Engine backtest and a cost-aware
buy-and-hold comparator. Both use the same candles, starting capital, fee rate,
and slippage assumption. The strategy can enter only after a BUY signal, at the
following candle open. The benchmark enters at the second candle open (the
earliest possible next-open execution) and stays long until the final candle
close. The report includes `strategy_minus_benchmark_return_pct`; a negative
value means the strategy underperformed this comparator in that evaluation
window. This comparison is descriptive, not proof of statistical significance.

This improves reproducibility but does not establish future profitability.
Freeze parameters before evaluating held-out data. The fee and slippage inputs
are assumptions and must be checked against the venue and market conditions.
