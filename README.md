
# Crypto Perpetuals Data Pipeline

A Python data engineering project for collecting, validating, normalizing, storing, and analyzing cryptocurrency perpetual futures market data.

The goal is to build a reliable historical dataset for studying price movements, open interest, trading activity, and market anomalies across perpetual futures contracts.

**Current status:** Working local ingestion and SQLite pipeline. Cloud infrastructure and analytics are being developed incrementally.

## Architecture

```text
Binance USDⓈ-M Futures REST API
                 |
                 v
          API ingestion
                 |
                 v
        Raw JSON responses
           data/raw/
                 |
                 v
       Validation / Normalization
                 |
                 v
          SQLite database
       data/db/market_data.sqlite3
                 |
                 v
       SQL joins and summaries
                 |
                 v
         Rich terminal output
```

The pipeline separates API retrieval, formatting, normalization, persistence, and execution control.

Raw API responses are saved before transformation, preserving the original source data for debugging and reprocessing.

## Implemented Features

### 1. Market Data Ingestion

Collects data for two Binance perpetual futures contracts:

- `BTCUSDT`
- `1000PEPEUSDT`

Uses three Binance USDⓈ-M Futures endpoints:

| Endpoint | Data |
|---|---|
| `/futures/data/openInterestHist` | Historical open interest |
| `/fapi/v1/klines` | OHLCV candlesticks |
| `/fapi/v1/exchangeInfo` | Contract specifications |

The initial data interval is five minutes.

API responses are saved as timestamped JSON files.

### 2. Validation and Normalization

Transforms Binance responses into structured records suitable for a relational database.

Current validation includes:

- Required fields and numeric values
- Five-minute candle duration and timestamp alignment
- OHLC price consistency
- Volume and taker-buy constraints
- Exclusion of unfinished candles
- Detection of older one-minute candle files

Financial decimal values are preserved as strings during normalization to avoid unnecessary floating-point conversion.

### 3. SQLite Storage

The local database keeps the original three observation/source tables and adds four reference/provenance tables:

| Table | Purpose |
|---|---|
| `raw_files` | Tracks source files, checksums, and retrieval metadata |
| `oi_observations` | Stores historical open interest observations |
| `price_candles` | Stores normalized five-minute OHLCV candles |
| `exchanges` | Identifies the Binance USDⓈ-M market |
| `assets` | Exchange-native base, quote and margin identifiers |
| `contracts` | Latest actual exchangeInfo specifications |
| `metadata_sources` | Saved specification payloads and provenance |

The loader uses unique keys and conflict-safe inserts to avoid duplicating previously stored observations.

Raw file checksums help detect unexpected changes to source files.

**Timestamp alignment:** Candles are assigned a five-minute period-end timestamp. Open interest observations with matching period-end timestamps can then be joined to the corresponding candles using the contract symbol and period boundary.

### 4. Terminal Interface

Uses Rich to provide:

- Muted, minimal terminal formatting
- Readable market data samples
- Contract metadata inspection
- Pipeline execution summaries
- Per-contract OI and candle counts
- Counts of aligned observations
- Quote-denominated taker volume delta
- Pastel-green indicators for newly added records

The current quote volume delta calculation is:

```text
Quote Delta = (2 × Taker Buy Quote Volume) - Total Quote Volume
```

This measures net aggressive buying versus selling volume within a candle. It is not cumulative volume delta (CVD), which will be implemented separately.

### 5. Online and Offline Execution

Online mode fetches new API responses and processes saved raw data.

Offline mode skips API requests and reprocesses existing raw files, making development and testing possible without requesting new market data.

## Project Structure

Implementation now lives in `src/crypto_pipeline/`, with separate Binance retrieval, normalization, storage, reporting, logging and CLI modules. The original scripts remain small compatibility entry points.

- [Data model, ER diagrams, units and CoinGecko plan](docs/data-model.md)
- [Installation, package layout, tests, logs and database safety](docs/operations.md)

## Getting Started

### Prerequisites

- Python 3
- Internet access for online ingestion
- Access to the relevant Binance public market-data endpoints

Binance API availability and permitted access vary by jurisdiction. The pipeline does not bypass geographic restrictions.

### Installation

Clone the repository and enter its directory:

```bash
git clone git@github.com:bybilal/crypto-perpetuals-data-pipeline.git
cd crypto-perpetuals-data-pipeline
```

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
```

### Run the Pipeline

Online mode:

```bash
python src/run_pipeline.py
```

Offline mode:

```bash
python src/run_pipeline.py --offline --human-log
```

Offline mode requires previously saved raw JSON files.

Raw data and SQLite databases are intentionally excluded from Git, so a fresh clone does not contain historical observations. Initial data collection requires access to the API or separately obtained source files.

## Earlier AWS Lambda Milestone

In October 2026, an earlier connectivity experiment successfully retrieved BTCUSDT perpetual futures candlestick data through AWS Lambda.

**Environment:**

- AWS Lambda with Python 3.14
- AWS Tokyo region (`ap-northeast-1`)
- Binance USDⓈ-M Futures REST API
- Amazon CloudWatch

### Single Test Invocation

| Metric | Result |
|---|---|
| HTTP response | 200 OK |
| API latency | 396.53 ms |
| Lambda duration | 398.73 ms |
| Memory used | 56 MB |
| Candlesticks retrieved | 2 |

These results describe one successful test invocation, not a production benchmark.

The current local SQLite pipeline is a separate development milestone and has not yet been integrated into the AWS deployment.

## Technology Stack

| Technology | Role | Status |
|---|---|---|
| Python | Ingestion and processing | Implemented |
| Binance REST API | Market data | Implemented |
| SQLite | Local relational storage | Implemented |
| Rich | Terminal presentation | Implemented |
| SQL | Data storage and joins | Implemented |
| AWS Lambda | Earlier connectivity experiment | Tested |
| Amazon CloudWatch | Earlier Lambda monitoring | Tested |
| pytest | Automated regression and data-quality tests | Implemented |
| Amazon S3 | Cloud raw-data storage | Planned |
| PostgreSQL | Cloud relational storage | Planned |
| CI/CD | Automated validation and deployment | Planned |
| Dashboard | Market analytics and visualization | Planned |

## Development Roadmap

### Completed

- Initial AWS Lambda API connectivity experiment
- Local Binance API ingestion
- Raw JSON preservation
- Five-minute market data normalization
- SQLite schema and ingestion
- Duplicate prevention
- Timestamp-based OI/candle alignment
- Offline execution mode
- Rich terminal summaries
- Packaged modules with compatible script entry points
- Pytest regression and data-quality tests
- Transactional schema upgrades with verified SQLite backups
- Actual exchangeInfo reference tables and provenance
- Structured JSONL and optional plain-text operational logs

### Next

- Add regular collection, recent-history backfilling and explicit gap detection
- Verify underlying-token multipliers against explicit primary specifications
- Review staged CoinGecko identity/category/valuation integration
- Add continuous collection and gap monitoring

### Analytics

- Price percentage changes
- Open interest percentage changes
- Rolling open interest Z-scores
- Cumulative volume delta (CVD)
- VWAP and volume-based statistics
- Cross-contract comparisons

### Future Infrastructure

- PostgreSQL migration
- Cloud object storage
- Scheduled ingestion
- CI/CD
- Dashboard
- Additional market data sources

## Current Limitations

- Only two perpetual futures contracts are configured.
- Underlying-token multipliers remain unset where exchangeInfo supplies no verified conversion.
- Historical open interest and candles are currently processed at a five-minute resolution.
- The latest candle's quote volume delta is displayed, but CVD is not yet calculated.
- Regression tests and per-run logs are implemented; production alerting and log retention are not.
- The local pipeline is not yet deployed as a scheduled cloud service.

This repository is an actively developed data engineering portfolio project.
