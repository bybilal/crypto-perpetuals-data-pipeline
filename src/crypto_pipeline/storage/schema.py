# Define the SQLite tables, keys and indexes; field meanings are in docs/data-model.md; store the result in SCHEMA.
SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_files (
    id INTEGER PRIMARY KEY,
    file_path TEXT NOT NULL UNIQUE,
    sha256 TEXT NOT NULL,
    symbol TEXT NOT NULL,
    dataset TEXT NOT NULL,
    interval TEXT NOT NULL,
    retrieved_at_ms INTEGER NOT NULL,
    record_count INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS oi_observations (
    symbol TEXT NOT NULL,
    source_timestamp_ms INTEGER NOT NULL,
    bucket_end_ms INTEGER,
    oi_quantity TEXT NOT NULL,
    oi_notional_quote TEXT NOT NULL,
    cmc_supply TEXT,
    raw_file_id INTEGER NOT NULL
        REFERENCES raw_files(id),

    PRIMARY KEY (symbol, source_timestamp_ms)
);

CREATE TABLE IF NOT EXISTS price_candles (
    symbol TEXT NOT NULL,
    open_ms INTEGER NOT NULL,
    close_ms INTEGER NOT NULL,
    bucket_end_ms INTEGER NOT NULL,

    open_price TEXT NOT NULL,
    high_price TEXT NOT NULL,
    low_price TEXT NOT NULL,
    close_price TEXT NOT NULL,

    base_volume TEXT NOT NULL,
    quote_volume TEXT NOT NULL,
    trade_count INTEGER NOT NULL,
    taker_buy_base TEXT NOT NULL,
    taker_buy_quote TEXT NOT NULL,

    raw_file_id INTEGER NOT NULL
        REFERENCES raw_files(id),

    PRIMARY KEY (symbol, open_ms)
);

CREATE INDEX IF NOT EXISTS idx_oi_bucket
ON oi_observations(symbol, bucket_end_ms);

CREATE INDEX IF NOT EXISTS idx_candle_bucket
ON price_candles(symbol, bucket_end_ms);
"""


