# Reproducible BTC/USDT Historical Data

An opt-in, credential-free downloader is provided in `btc_signal_lab.market_data`.
It requests public Binance Spot OHLCV candles; it does not require API keys and
is separate from signal generation and backtesting.

Example from the repository root:

```python
from btc_signal_lab.market_data import download_binance_klines, save_dataset

rows = download_binance_klines(
    "BTCUSDT", "1h",
    "2025-01-01T00:00:00Z",
    "2025-02-01T00:00:00Z",
)
manifest = save_dataset(
    rows, "data/btcusdt_1h_2025-01.csv",
    symbol="BTCUSDT", interval="1h",
    start="2025-01-01T00:00:00Z",
    end="2025-02-01T00:00:00Z",
)
print(manifest)
```

The end timestamp is exclusive and both endpoints must align to the candle interval.
The downloader checks OHLC consistency, finite values, duplicate timestamps, gaps,
and expected row count, then writes a CSV and adjacent JSON manifest with source,
retrieval time, date range, row count, and SHA-256. Empty or incomplete ranges fail
closed rather than being silently accepted. Supported intervals are 1h, 4h, and 1d.

Before evaluating strategy performance, preserve the dataset and manifest, choose
a fixed train/evaluation split, and report fees/slippage assumptions. Do not tune
rules on the held-out evaluation period. No historical performance claim is made
until the resulting dataset is downloaded and backtested.
