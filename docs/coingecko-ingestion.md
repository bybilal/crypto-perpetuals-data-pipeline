# Manual Bitcoin ingestion (Phase 2B)

Run from the repository with its virtual environment activated:

```bash
python -m crypto_pipeline.coingecko_cli --human-log
```

This separate command makes two requests: `/coins/bitcoin` for USD market data and category membership, and `/coins/categories/list` for provider category IDs. It never runs from the Binance scheduler. No paid API host or subscription is used.

## Access and attribution

Checked 2026-11-06: CoinGecko documents a [keyless public API](https://docs.coingecko.com/docs/keyless-public-api) suitable for testing, with a shared dynamic limit around five calls/minute. The first real capture succeeded without a key. Keyless availability is not a production guarantee. The [Demo plan](https://www.coingecko.com/en/api) currently advertises 100 calls/minute and 10,000 monthly credits; consult your account for actual limits. A free Demo key can be supplied as `COINGECKO_DEMO_API_KEY` in the process environment; it is sent only in the `x-cg-demo-api-key` header. Do not paste keys into Git or this chat. `.env` files are not automatically loaded. No subscription was purchased or account created.

Endpoint references: [coin details](https://docs.coingecko.com/reference/coins-id), [category ID map](https://coingecko-api-v3.readme.io/v3.0.1/reference/coins-categories-list), [membership guidance](https://support.coingecko.com/articles/2196181997-how-do-i-get-a-list-of-categories-tagged-to-a-coin). Data provided by [CoinGecko](https://www.coingecko.com).

Timeout is 30 seconds/request; transient errors and 429 receive at most three attempts with 15/30-second backoff. Numeric Retry-After is respected; waits over 60 seconds or HTTP-date Retry-After stop for a later manual retry. Authentication/access failures stop immediately. Headers and provider error bodies are not logged. No alternate-host workaround is used.

## Storage and replay

Original response bytes are saved under `data/raw/coingecko/<capture-id>/`; a manifest records endpoints, independent retrieval times and SHA-256 checksums. Incomplete captures retain their received bytes but cannot ingest without a complete manifest. The directory is ignored by Git.

```bash
python -m crypto_pipeline.coingecko_cli --replay data/raw/coingecko/bb3865fca08e46b48959915ed57afe4c --human-log
```

Replay makes no network requests. Paths `--db-path`, `--raw-dir`, and `--log-dir` can be overridden for isolated work. Fetching does not hold the database lock; the short migration/load transaction shares the Binance lock. If collection is active, retry ingestion using the printed capture path. A failed command returns exit code 1 and logs a failed event. Normal completion produces structured JSONL and optional plain text logs, plus a minimal Rich summary.

The provider's **market_data.last_updated** is stored independently of retrieval; unavailable timestamps stay NULL. JSON numbers are parsed directly as Decimal, without a float intermediate. Missing measurements stay NULL; only USD currency fields are selected. No Binance observations or USDT amounts are converted.

Two market_sources rows retain response paths, checksums and retrieval times. The Bitcoin snapshot references the Bitcoin response. Categories reference the category-definition response; memberships reference the Bitcoin response. Exact category names are resolved only when the definition list provides one unambiguous ID; missing/ambiguous mappings fail atomically rather than inventing slugs. Existing category names remain first-seen definitions; provider renames require a future explicit policy. The manifest preserves the pair of responses used for each capture.

Duplicate processing of the same capture path verifies both digest and retrieval timestamp and leaves existing rows unchanged. New capture directories create historical snapshots even if the provider's cached values/timestamp have not changed. Absolute source paths identify captures; moving/copying raw directories is not currently a portable deduplication mechanism. Keep them at their original location. No effective-dated category-removal inference is performed.

## First actual rows

Capture `bb3865fca08e46b48959915ed57afe4c` inserted:

- market_sources IDs **1** (Bitcoin) and **2** (category definitions), retrieval milliseconds **1794012219124** and **1794012220491**.
- One market_snapshots row: provider coingecko, coin bitcoin, source_id 1, currency USD, provider timestamp **1794012113000**.
- Eight categories with source_id 2, and eight Bitcoin memberships with source_id 1: `bitcoin-ecosystem`, `coinbase-50-index`, `ftx-holdings`, `gmci-30-index`, `gmci-index`, `layer-1`, `proof-of-work-pow`, `smart-contract-platform`.

| Measurement | Exact stored decimal text | Unit |
|---|---|---|
| price | 75875 | USD/BTC |
| market_cap | 1525696565665 | USD |
| fdv | 1525708705883 | USD |
| circulating_supply | 20107665.0 | BTC |
| total_supply | 20107825.0 | BTC |
| max_supply | 21000000.0 | BTC |
| volume_24h | 28844731339 | USD |

These are source observations, not recomputed valuations. FDV methodology remains provider-defined; do not substitute price × maximum supply or force equality. Collection time differs from provider update time. No PEPE data or joins were added; its native mapping remains pending and multiplier NULL.

## Verification

105 deterministic tests passed. Tests cover precision, nulls, timestamps, unsupported coins, category ambiguity, mappings, checksums, duplicate and new captures, HTTP failures/rate limits, header authentication, offline CLI/logs and relational integrity. Live integrity was OK with zero FK violations. Both source checksums matched, manual replay inserted zero snapshots, and two ordinary Binance offline replays preserved all 14 tables. Scheduler inspection showed 37 executions with last exit code 0.

```bash
python -m pytest -q
python scripts/validate_pipeline.py
python -m crypto_pipeline.schedule status
sqlite3 data/db/market_data.sqlite3 'SELECT * FROM market_snapshots;'
sqlite3 data/db/market_data.sqlite3 'PRAGMA integrity_check; PRAGMA foreign_key_check;'
```

The existing validation script audits Binance raw-file lineage and compares all table rows; it does not independently validate CoinGecko provenance. CoinGecko replay verifies its capture checksums and identity. Automated tests use mocks only. No schema changes, jobs, cloud infrastructure, backfills or analytics were introduced.
