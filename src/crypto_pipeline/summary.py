from .units import quote_delta
from .reporting import console, display_metric, display_market_summary
from .storage.queries import database_snapshot
from .time_utils import utc_label
from .config import SYMBOLS

def display_summary(connection, stats, before, db_path=None):
    """Show cumulative totals and this run's increases."""

    after = database_snapshot(connection)

    console.print()
    console.print(
        "[#8EAABD]SQLite / Normalization / 5m[/#8EAABD]"
    )
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
        display_metric(label, stats[key])

    if stats.get("file_errors", 0):
        display_metric("File errors", stats["file_errors"])

    rows = []

    for symbol in SYMBOLS:

        current = after["contracts"][symbol]
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

        latest = "—"
        delta_label = "—"

        if candle:
            bucket_end, total_quote, taker_buy_quote = candle

            # Quote-denominated volume delta.
            delta = quote_delta(total_quote, taker_buy_quote)

            latest = utc_label(
                bucket_end
            ).removesuffix(" UTC")

            delta_label = f"{delta:+,.2f}"

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

    console.print()

    display_market_summary(rows)

    console.print()
    console.print(
        f"[grey62]Database:[/grey62] {db_path or 'data/db/market_data.sqlite3'}"
    )


