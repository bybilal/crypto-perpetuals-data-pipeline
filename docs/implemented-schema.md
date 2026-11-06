# Implemented SQLite schema (version 2)

Generated from the audited database PRAGMAs on 2026-11-06T22:20:33.350010+00:00. No schema changes were made during Phase 1.

Solid relationships below are actual SQLite foreign keys. The observation-to-contract relationship and OI-to-candle boundary join are application queries, not enforced foreign keys. All financial decimal values are TEXT; timestamps are INTEGER Unix milliseconds.

```mermaid
erDiagram
    exchanges ||--o{ assets : exchange_id
    exchanges ||--o{ contracts : exchange_id
    assets ||--o{ contracts : base_asset_id
    assets ||--o{ contracts : quote_asset_id
    assets ||--o{ contracts : margin_asset_id
    metadata_sources ||--o{ contracts : source_id
    raw_files ||--o{ oi_observations : raw_file_id
    raw_files ||--o{ price_candles : raw_file_id
    assets {
        TEXT asset_id PK
        TEXT exchange_id FK
        TEXT native_symbol
    }
    contracts {
        TEXT symbol PK
        TEXT exchange_id FK
        TEXT base_asset_id FK
        TEXT quote_asset_id FK
        TEXT margin_asset_id FK
        TEXT contract_type
        TEXT status
        TEXT price_tick
        TEXT quantity_step
        TEXT contract_size
        TEXT underlying_multiplier
        TEXT multiplier_evidence
        INTEGER source_id FK
        INTEGER retrieved_at_ms
        TEXT specification_json
    }
    exchanges {
        TEXT exchange_id PK
        TEXT name
        TEXT market_type
    }
    metadata_sources {
        INTEGER id PK
        TEXT file_path
        TEXT sha256
        INTEGER retrieved_at_ms
        TEXT payload_json
    }
    oi_observations {
        TEXT symbol PK
        INTEGER source_timestamp_ms PK
        INTEGER bucket_end_ms
        TEXT oi_quantity
        TEXT oi_notional_quote
        TEXT cmc_supply
        INTEGER raw_file_id FK
    }
    price_candles {
        TEXT symbol PK
        INTEGER open_ms PK
        INTEGER close_ms
        INTEGER bucket_end_ms
        TEXT open_price
        TEXT high_price
        TEXT low_price
        TEXT close_price
        TEXT base_volume
        TEXT quote_volume
        INTEGER trade_count
        TEXT taker_buy_base
        TEXT taker_buy_quote
        INTEGER raw_file_id FK
    }
    raw_files {
        INTEGER id PK
        TEXT file_path
        TEXT sha256
        TEXT symbol
        TEXT dataset
        TEXT interval
        INTEGER retrieved_at_ms
        INTEGER record_count
    }
```

Composite primary keys: `oi_observations(symbol, source_timestamp_ms)` and `price_candles(symbol, open_ms)`. Unique constraints: `raw_files.file_path`, `metadata_sources.file_path`, `assets(exchange_id, native_symbol)`. Explicit nonunique query indexes: `idx_oi_bucket(symbol, bucket_end_ms)` and `idx_candle_bucket(symbol, bucket_end_ms)`. SQLite also creates indexes for the TEXT/composite primary keys and unique constraints. Integer primary keys alias the row ID.

Nullable non-key fields: `oi_observations.bucket_end_ms`, `oi_observations.cmc_supply`, `contracts.contract_size`, `contracts.underlying_multiplier`, `contracts.multiplier_evidence`. Other non-key fields are NOT NULL. SQLite rowid-table TEXT primary keys are not explicitly NOT NULL in this schema; ingestion validates identities, but direct SQL can bypass those checks.

`raw_files` indexes disk captures and checksums; it does **not** contain the market JSON payload. `metadata_sources` stores both the disk-source reference and original exchangeInfo payload. Contracts retain the latest selected specification; older full exchangeInfo snapshots remain in metadata_sources. Each observation retains its first accepted source ID.

The logical market join is `o.symbol = k.symbol AND o.bucket_end_ms = k.bucket_end_ms`. Joining only by symbol would multiply unrelated periods. Unaligned OI retains its source timestamp and NULL bucket end; it does not join.

Before multiple exchanges, introduce exchange-scoped contract IDs in observation keys and references. Before CoinGecko, introduce canonical identities and verified provider mappings: `binance_usdm:1000PEPE` is exchange-native, not a universal coin identity. Review explicit NOT NULL/CHECK constraints and enforce observation-to-contract references in a separately backed-up migration. No such migration is included here.
