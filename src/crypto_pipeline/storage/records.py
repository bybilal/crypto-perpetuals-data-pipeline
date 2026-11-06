"""Fixed-schema insertion. Natural keys retain the first valid observation."""
# Build the named fields used by this operation; store the result in COLUMNS.
COLUMNS = {
    "oi_observations": ("symbol", "source_timestamp_ms", "bucket_end_ms", "oi_quantity", "oi_notional_quote", "cmc_supply"),
    "price_candles": ("symbol", "open_ms", "close_ms", "bucket_end_ms", "open_price", "high_price", "low_price", "close_price", "base_volume", "quote_volume", "trade_count", "taker_buy_base", "taker_buy_quote"),
}


# Define insert observation with the inputs listed below.
def insert_observation(connection, table, row, raw_file_id):
    # Calculate COLUMNS[table] + ('raw_file_id',); store the result in columns.
    columns = COLUMNS[table] + ("raw_file_id",)
    # Calculate [row[key] for key in columns[:-1]] + [raw_file_id]; store the result in values.
    values = [row[key] for key in columns[:-1]] + [raw_file_id]
    # Table and column names come exclusively from the allowlist above.
    statement = f"INSERT OR IGNORE INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})"
    # Return connection.execute(statement, values).rowcount to the caller.
    return connection.execute(statement, values).rowcount
