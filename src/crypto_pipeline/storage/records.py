"""Fixed-schema insertion. Natural keys retain the first valid observation."""
COLUMNS = {
    "oi_observations": ("symbol", "source_timestamp_ms", "bucket_end_ms", "oi_quantity", "oi_notional_quote", "cmc_supply"),
    "price_candles": ("symbol", "open_ms", "close_ms", "bucket_end_ms", "open_price", "high_price", "low_price", "close_price", "base_volume", "quote_volume", "trade_count", "taker_buy_base", "taker_buy_quote"),
}


def insert_observation(connection, table, row, raw_file_id):
    columns = COLUMNS[table] + ("raw_file_id",)
    values = [row[key] for key in columns[:-1]] + [raw_file_id]
    # Table and column names come exclusively from the allowlist above.
    statement = f"INSERT OR IGNORE INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})"
    return connection.execute(statement, values).rowcount
