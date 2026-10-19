# Binance Spot aggTrades investigation: 2023-03-24 BTCUSDT gap

**Status:** unresolved source-coverage blocker. This report is a separate research/sensitivity record and does not modify or certify the canonical kline dataset.

## Question

Can the official Binance Spot BTCUSDT aggregate-trade archive reconstruct the 80 missing one-minute kline intervals from 2023-03-24 12:40:00 through 13:59:59 UTC?

## Retrieval evidence

Retrieved by GitHub Actions on 2026-10-18 UTC.

| Source | HTTP | Downloaded bytes | SHA-256 |
|---|---:|---:|---|
| [Official daily aggTrades ZIP](https://data.binance.vision/data/spot/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-2023-03-24.zip) | 200 | 16,372,366 | `e4a0626d79f7476485c8eb71caf466ebb939c6863300cc4456ba27ff13914241` |
| [Official daily 1m kline ZIP](https://data.binance.vision/data/spot/daily/klines/BTCUSDT/1m/BTCUSDT-1m-2023-03-24.zip) | 200 | 65,200 | `305d0f6cdb8a6cfd8063a7d48c66f14b33727d934857746d549663e94b41312d` |

The aggTrades archive contains 1,142,284 rows. Aggregate-trade IDs are continuous from 2,583,723,514 through 2,584,865,797 and no timestamp regressions were observed. However, timestamp coverage is incomplete:

- Last aggregate trade before the target interval: ID `2584169633` at **2023-03-24 11:27:23.146 UTC**.
- First aggregate trade at/after 14:00 UTC: ID `2584169634` at **2023-03-24 14:00:00.062 UTC**.
- The two IDs are consecutive, but timestamps jump by **9,156,916 ms (2 h 32 min 36.916 s)**.
- Rows observed from 12:40:00 to 13:59:59 UTC: **0**.
- Candidate reconstructed minutes in the requested 80-minute interval: **0/80**. The tool does not fabricate empty-minute bars.

The 14:00 UTC reconstructed bar exactly matches the official kline for OHLC, base volume, quote volume, taker-buy base/quote volumes, and underlying trade count (7,682). This confirms that the aggregate-trade reconstruction logic can reconcile a boundary candle, but does not establish coverage or recoverability inside the missing interval. The 12:39 comparison is also unavailable from aggTrades because the source time gap begins earlier.

## Independent raw individual-trades check

A second isolated diagnostic was added at `scripts/research_raw_trades_gap.py` and run against the official daily Spot individual-trades archive:

- Archive: [BTCUSDT-trades-2023-03-24.zip](https://data.binance.vision/data/spot/daily/trades/BTCUSDT/BTCUSDT-trades-2023-03-24.zip)
- The archive returned HTTP 200, downloaded **22,008,845 bytes**, SHA-256 `bceaa0b664b055318c22e509d33c04d532da143e7de41ca2fc3457100439c587`, and contained **1,511,137 individual-trade rows**.
- Individual trade IDs were continuous and timestamps had no regressions.
- Rows from 12:40:00 through 13:59:59 UTC: **0**; reconstructed target minutes: **0/80**.
- The largest adjacent-trade timestamp gap was the same **9,156,916 ms** from 11:27:23.146 UTC to 14:00:00.062 UTC.
- Thus the raw individual-trades archive independently exhibits the same coverage gap as aggTrades; it does not supply trades from which the missing bars could be reconstructed.

The combined workflow completed successfully in [run 39171923501](https://github.com/mohammadshahshahi/btc-signal-lab/actions/runs/39171923501), using commit `7bd5f1ef16e3a70f202e437fc750b22958aaacec`. Its artifact is available from that run. This run includes the source hash above.

## Official monthly 1m kline archive cross-check

To test whether the gap was only a defect in the daily ZIP, the official March monthly 1m kline archive was downloaded and compared with every daily kline row and each of the 80 target minutes:

- Archive: [BTCUSDT-1m-2023-03.zip](https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2023-03.zip)
- HTTP 200; 2,300,446 downloaded bytes; SHA-256 `5591171a15f210af647a2fb68ab8cbad45a3a595cfe9a0eec9d06e5e84928bec`.
- Monthly archive rows: **44,560**; expected for 31 complete UTC days: **44,640**.
- Target interval present in monthly archive: **0/80 minutes**; missing: **80/80 minutes**.
- Daily-vs-monthly comparison: **0 mismatches** across all daily rows present in the daily archive.
- HEAD-only metadata probes confirmed the monthly raw-trades and aggTrades objects exist, but advertised sizes are approximately **1.36 GB** and **2.66 GB** respectively. Their bodies were deliberately not downloaded merely to repeat the already-observed daily-source gap; this size check is recorded in the JSON evidence artifact.

This cross-check rules out the narrower explanation that the 80-minute omission exists only in the daily kline ZIP: the official monthly kline ZIP reproduces the same omission. It does **not** establish why Binance's archived sources omit those minutes, and it does not justify synthesizing candles.

Evidence workflow: [run 39217593146](https://github.com/mohammadshahshahi/btc-signal-lab/actions/runs/39217593146) (successful). It contains the monthly archive checksum, row count, exact coverage result, and monthly-source size probes.

## Verdict

**Both official daily Spot aggTrades and individual-trades archives are insufficient to reconstruct this interval; the official monthly 1m kline archive also omits the same 80 minutes and exactly agrees with the incomplete daily archive on every overlapping row.** The fact that aggregate-trade IDs are continuous does not compensate for the 2.5-hour timestamp gap. The official kline source remains incomplete (1,360 rows rather than 1,440 for the UTC day), and the strict historical validation gate remains **FAILED**.

- Do not patch the primary kline dataset with this artifact.
- Do not interpolate, create empty candles, or mix exchanges.
- Do not claim Recovery/1h historical validation passed.
- Keep PR #12 Draft/unmerged until an independently verifiable, protocol-compliant source is found or the blocker is explicitly accepted as unresolved.
- The evidence workflow is [run 39112022325](https://github.com/mohammadshahshahi/btc-signal-lab/actions/runs/39112022325); the report and empty sensitivity CSV are available in its artifact.

## Reproduction

Run the GitHub Actions workflow **Binance Historical Gap Evidence (Research Only)** on branch `research/aggtrades-gap-evidence`. It retrieves official aggTrades, individual-trades, and 1m kline ZIPs; validates schema/order, hashes raw sources, checks timestamp coverage and candle reconstruction, and emits JSON reports plus segregated sensitivity CSVs. The report always sets `strict_primary_kline_gate_passed: false`.
