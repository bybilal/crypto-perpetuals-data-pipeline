# Local analytics dashboard

This Streamlit + Plotly prototype reads the existing SQLite database. It does not fetch data, ingest records, migrate the schema, or change the collector schedule.

## Launch

From the repository directory:

```sh
source .venv/bin/activate
python -m pip install -e '.[dashboard,dev]'
python -m streamlit run dashboard.py --server.address 127.0.0.1 --server.port 8501 --server.headless true --browser.gatherUsageStats false
```

Open http://127.0.0.1:8501. Keep the terminal running; Ctrl-C stops only the dashboard. Choose a UTC date and contract in the sidebar. Refresh database reruns the read-only queries.

## Four views and their tables

| View | SQL evidence | Interpretation |
| --- | --- | --- |
| Data quality | `price_candles`, `oi_observations`, `monitoring_windows`, `observation_gaps` | Each square is a five-minute **end boundary**. Actual rows establish presence; recovered gap history marks recovered rows. Missing rows before monitoring starts are outside scope. Recent absent candles receive one minute of grace; OI receives ten minutes. Future boundaries are pending. Hover for UTC time and raw-file ID. |
| OI scanner | `price_candles`, `oi_observations` | Two contract points at the selected historical boundary; incomplete histories suppress the affected point. |
| Market timeline | `price_candles`, `oi_observations` | Separate price, native OI quantity, and USDT traded-volume panels. Missing grid slots break lines. |
| Asset/source inspector | `contracts`, `asset_mappings`, `provider_assets`, `market_snapshots`, `market_sources`, `raw_files`, `run_sources`, `pipeline_runs` | Verified mappings gate fundamentals joins. Source records and run IDs provide inspection evidence, not proof of completeness. |

## Indicator definition

For a horizon of H five-minute bars, OI change is `100 × (OI[t] / OI[t-H] − 1)`. The Z-score compares the selected change with the preceding N changes, excluding the current change, using sample standard deviation (N−1 denominator). Price change uses the same horizon.

The calculation requires H+N+1 consecutive OI levels and the two endpoint prices. Missing observations, insufficient history, nonpositive denominators, and zero baseline variance produce an explicit message. Overlapping horizons make baseline changes correlated: this is a descriptive indicator, not a probability or a trading signal. An above-baseline OI change can still be negative. Price/OI combinations do not identify long/short positions or prove liquidations.

The default analysis time uses the latest common OI boundary capped by the latest candle boundary. The sidebar date still controls the analysis date; users can select another time.

## Units and safety

Database monetary strings remain unchanged. Indicators use Decimal arithmetic; chart values become floating-point numbers only for visualization. Binance prices and traded volume use USDT; CoinGecko fundamentals use USD. No conversion between them is assumed. Native `1000PEPE` OI is not converted into individual PEPE tokens. Its identity mapping remains pending and its unknown multiplier is preserved.

`src/crypto_pipeline/analytics.py` contains the read-only queries and calculations; `dashboard.py` contains UI composition. Connections use SQLite `mode=ro` plus `query_only`, with short read transactions. The dashboard imports no ingestion or migration path.

## Verification and prototype limits

121 pytest tests pass, including deterministic classification, indicator, missing-grid, and read-only connection checks. Streamlit AppTest renders all four tabs against stored data for BTCUSDT and 1000PEPEUSDT. Browser review covered all four views during implementation. SQLite integrity and foreign keys are checked separately.

The timeline shows one UTC day at a time. Refresh is manual. Candle age is displayed and warns after 15 minutes; inspect individual source timestamps for fundamentals freshness. Fundamental source timestamps remain Unix milliseconds. The inspector does not rehash raw files. Separate query blocks may observe different snapshots if collection completes during rendering. Pending future cells are not evidence of collection failure; an absent OI row does not establish its cause. No automatic recovery, analytics alerts, market profiles, deployment, or scheduler changes are included.
