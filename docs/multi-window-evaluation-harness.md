# Multi-window evaluation harness

## Purpose
`btc_signal_lab.multi_window` orchestrates deterministic research evaluation across explicitly ordered, frozen BTCUSDT datasets. It does not download data, schedule jobs, persist state, or alter Signal Engine v1.1 parameters.

## Input contract
Each item supplied to `evaluate_windows()` must include:
- `name`: unique window identifier
- `partition`: `train`, `validation`, or `test`
- `csv_path`: local normalized CSV path with adjacent `.manifest.json`
- `interval`: `1h` or `4h`
- `start_utc`: inclusive candle-open boundary
- `end_utc_exclusive`: exclusive boundary

Windows must be supplied in chronological order and cannot overlap. If a test partition is present, it must be unique and last. The manifest must match BTCUSDT, interval, and exact UTC boundaries; the existing verified-dataset loader validates row count, SHA-256, OHLCV and continuity.

## Output
The report contains per-window strategy results, cost-aware buy-and-hold, flat cash, data provenance, assumptions, and a separately labelled forward-horizon diagnostic. Wall-clock generation timestamps are omitted from the multi-window report so identical frozen inputs, code commit, and parameters produce byte-identical JSON.

## Reproducibility and safety
- Unit tests use local fixtures only; no network calls.
- The caller must provide the evaluated code commit.
- Defaults remain 10,000 initial capital, 0.1% fee per side, and 5 bps slippage per side.
- No live trading, API credentials, or private keys.
- The harness does not prove a window is untouched. Both contributors must attest that the final-test data/results have not been inspected or used before they are downloaded or evaluated.

## Example
```python
from btc_signal_lab.multi_window import evaluate_windows, write_multi_window_report

windows = [
    {
        "name": "bear-development-1h",
        "partition": "train",
        "csv_path": "data/bear_1h.csv",
        "interval": "1h",
        "start_utc": "2021-11-01T00:00:00Z",
        "end_utc_exclusive": "2022-11-01T00:00:00Z",
    },
    # Add only approved, frozen datasets in chronological order.
]
report = evaluate_windows(windows, code_commit="FULL_GIT_COMMIT_SHA")
write_multi_window_report(report, "reports/multi-window.json")
```

Do not use candidate final-test data until Issue #2 records approval from both contributors.
