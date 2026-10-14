# Crypto Perpetuals Data Pipeline

A Python-based data engineering project for ingesting, validating, storing, and analyzing cryptocurrency perpetual futures market data.

**Current status:** Phase 1 — API connectivity validated.

## Project Goals

Build an end-to-end market-data pipeline using Python, REST APIs, AWS cloud infrastructure, PostgreSQL/TimescaleDB, and analytical dashboards.

Planned analytics include VWAP-based relative strength, open interest statistics, and bid-ask spread monitoring.

## Milestone 1 — Binance API Connectivity (Completed)

Successfully deployed a Python AWS Lambda function that retrieves BTCUSDT perpetual futures market data from Binance's USDⓈ-M Futures REST API.

**Implemented:**
- AWS Lambda deployment using Python 3.14 in the Tokyo region (`ap-northeast-1`).
- Public REST API connectivity and HTTP error handling.
- Retrieval of BTCUSDT 30-minute candlestick data.
- API latency measurement.
- Execution monitoring and log inspection using Amazon CloudWatch.

### Test Results — October 2026

| Metric | Result |
|---|---|
| HTTP status | 200 OK |
| API latency | 396.53 ms |
| Lambda execution duration | 398.73 ms |
| Memory used | 56 MB |
| Candlesticks retrieved | 2 |

These results represent a single successful test invocation, not a production performance benchmark.

## Technology Stack

| Technology | Purpose | Status |
|---|---|---|
| Python | API integration | In progress |
| Binance REST API | Market-data source | Tested |
| AWS Lambda | Serverless ingestion | Tested |
| Amazon CloudWatch | Execution logs | Tested |
| Amazon S3 | Raw data storage | Planned |
| PostgreSQL / TimescaleDB | Structured historical data | Planned |
| Streamlit | Market analytics dashboard | Planned |

## Next Milestone

Persist API responses to Amazon S3, introduce data validation, and prepare the ingestion function for automated execution.

*This project is under active development.*