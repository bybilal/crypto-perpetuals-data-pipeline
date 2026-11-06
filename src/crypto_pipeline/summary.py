# Import quote_delta from .units for use below.
from .units import quote_delta
# Import console, display_metric, display_market_summary from .reporting for use below.
from .reporting import console, display_metric, display_market_summary
# Import database_snapshot from .storage.queries for use below.
from .storage.queries import database_snapshot
# Import utc_label from .time_utils for use below.
from .time_utils import utc_label
# Import SYMBOLS from .config for use below.
from .config import SYMBOLS

# Show cumulative totals and this run's increases.
def display_summary(connection, stats, before, db_path=None):
    """Show cumulative totals and this run's increases."""

    # Read cumulative source, observation, candle and aligned-pair counts; store the result in after.
    after = database_snapshot(connection)

    # Write the formatted output to the terminal.
    console.print()
    # Write the formatted output to the terminal.
    console.print(
        "[#8EAABD]SQLite / Normalization / 5m[/#8EAABD]"
    )
    # Write the formatted output to the terminal.
    console.print()

    # Raw file count is cumulative.
    display_metric(
        "Raw files indexed",
        after["raw_files"],
        after["raw_files"] - before["raw_files"],
    )

    # These metrics already describe this execution.
    for label, key in [
        ("New OI observations", "oi_inserted"),
        ("New five-minute candles", "candles_inserted"),
        ("Older 1m files skipped", "one_minute_files_skipped"),
        (
            "Unfinished candles skipped",
            "incomplete_candles_skipped",
        ),
        ("Invalid records", "invalid_records"),
    ]:
        # Show this metric and any positive growth using the configured Rich styles.
        display_metric(label, stats[key])

    # Enter this branch only when stats.get('file_errors', 0).
    if stats.get("file_errors", 0):
        # Show this metric and any positive growth using the configured Rich styles.
        display_metric("File errors", stats["file_errors"])

    # Build the ordered collection used by this operation; store the result in rows.
    rows = []

    # Process each symbol from SYMBOLS.
    for symbol in SYMBOLS:

        # Read after['contracts'][symbol] from the source data; store the result in current.
        current = after["contracts"][symbol]
        # Read before['contracts'][symbol] from the source data; store the result in previous.
        previous = before["contracts"][symbol]

        # Retrieve the newest completed candle.
        candle = connection.execute(
            """
            SELECT
                bucket_end_ms,
                quote_volume,
                taker_buy_quote
            FROM price_candles
            WHERE symbol = ?
            ORDER BY open_ms DESC
            LIMIT 1
            """,
            (symbol,),
        ).fetchone()

        # Use the explicit text '—'; store the result in latest.
        latest = "—"
        # Use the explicit text '—'; store the result in delta_label.
        delta_label = "—"

        # Enter this branch only when candle.
        if candle:
            # Use candle; store the result in (bucket_end, total_quote, taker_buy_quote).
            bucket_end, total_quote, taker_buy_quote = candle

            # Quote-denominated volume delta.
            delta = quote_delta(total_quote, taker_buy_quote)

            # Remove the known trailing label from the displayed timestamp; store the result in latest.
            latest = utc_label(
                bucket_end
            ).removesuffix(" UTC")

            # Build the text using the current field values; store the result in delta_label.
            delta_label = f"{delta:+,.2f}"

        # Add this item to the accumulating list.
        rows.append({
            "symbol": symbol,

            "oi_count": current["oi"],
            "oi_added": (
                current["oi"] - previous["oi"]
            ),

            "candle_count": current["candles"],
            "candles_added": (
                current["candles"] - previous["candles"]
            ),

            "matched_count": current["aligned"],
            "matched_added": (
                current["aligned"] - previous["aligned"]
            ),

            "latest": latest,
            "delta": delta_label,
        })

    # Write the formatted output to the terminal.
    console.print()

    # Render the per-contract counts, latest timestamps and quote deltas.
    display_market_summary(rows)

    # Write the formatted output to the terminal.
    console.print()
    # Write the formatted output to the terminal.
    console.print(
        f"[grey62]Database:[/grey62] {db_path or 'data/db/market_data.sqlite3'}"
    )


