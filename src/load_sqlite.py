
import hashlib
import json
import re
import sqlite3

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from normalize_market_data import (
    normalize_oi,
    normalize_kline,
)

from format_market_data import (
    console,
    display_market_summary,
    display_metric,
)


# ----------------------------------------
# PATHS AND CONFIGURATION
# ----------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent

PROJECT_ROOT = (
    SCRIPT_DIR.parent
    if SCRIPT_DIR.name == "src"
    else SCRIPT_DIR
)

RAW_DIR = PROJECT_ROOT / "data" / "raw"
DB_PATH = PROJECT_ROOT / "data" / "market_data.sqlite3"

DB_PATH.parent.mkdir(parents=True, exist_ok=True)

FILENAME_PATTERN = re.compile(
    r"^(BTCUSDT|1000PEPEUSDT)_(oi|klines)_"
    r"(\d{8}T\d{6}(?:\d{6})?Z)\.json$"
)

SYMBOLS = ("BTCUSDT", "1000PEPEUSDT")


# ----------------------------------------
# TIMESTAMP HELPERS
# ----------------------------------------

def filename_timestamp_ms(value):
    """Read the UTC retrieval time from a filename."""

    pattern = (
        "%Y%m%dT%H%M%S%fZ"
        if len(value) == 22
        else "%Y%m%dT%H%M%SZ"
    )

    dt = datetime.strptime(value, pattern)
    dt = dt.replace(tzinfo=timezone.utc)

    return int(dt.timestamp() * 1000)


def utc_label(milliseconds):
    """Convert milliseconds to a readable UTC timestamp."""

    dt = datetime.fromtimestamp(
        milliseconds / 1000,
        tz=timezone.utc,
    )

    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def detect_interval(dataset, records):
    """Distinguish older 1m files from 5m candle files."""

    if dataset == "oi":
        return "5m"

    if not records:
        return "unknown"

    try:
        durations = {
            int(row[6]) - int(row[0]) + 1
            for row in records
        }

    except (TypeError, IndexError, ValueError):
        return "unknown"

    if durations == {300_000}:
        return "5m"

    if durations == {60_000}:
        return "1m"

    return "unknown"


# ----------------------------------------
# SQLITE SCHEMA
# ----------------------------------------

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


# ----------------------------------------
# DATABASE SNAPSHOTS
# ----------------------------------------

def database_snapshot(connection):
    """
    Capture database counts before or after ingestion.

    Used to calculate per-run growth indicators.
    """

    snapshot = {
        "raw_files": connection.execute(
            "SELECT COUNT(*) FROM raw_files"
        ).fetchone()[0],
        "contracts": {},
    }

    for symbol in SYMBOLS:

        oi = connection.execute(
            """
            SELECT COUNT(*)
            FROM oi_observations
            WHERE symbol = ?
            """,
            (symbol,),
        ).fetchone()[0]

        candles = connection.execute(
            """
            SELECT COUNT(*)
            FROM price_candles
            WHERE symbol = ?
            """,
            (symbol,),
        ).fetchone()[0]

        aligned = connection.execute(
            """
            SELECT COUNT(*)
            FROM oi_observations AS oi
            JOIN price_candles AS k
              ON oi.symbol = k.symbol
             AND oi.bucket_end_ms = k.bucket_end_ms
            WHERE oi.symbol = ?
            """,
            (symbol,),
        ).fetchone()[0]

        snapshot["contracts"][symbol] = {
            "oi": oi,
            "candles": candles,
            "aligned": aligned,
        }

    return snapshot


# ----------------------------------------
# LOAD RAW FILES
# ----------------------------------------

def load_files(connection):
    """Normalize saved JSON and insert valid 5m observations."""

    stats = {
        "raw_files": 0,
        "oi_inserted": 0,
        "candles_inserted": 0,
        "one_minute_files_skipped": 0,
        "incomplete_candles_skipped": 0,
        "invalid_records": 0,
    }

    for path in sorted(RAW_DIR.glob("*.json")):

        match = FILENAME_PATTERN.match(path.name)

        if not match:
            continue

        symbol, dataset, timestamp_text = match.groups()

        try:
            raw_bytes = path.read_bytes()
            data = json.loads(raw_bytes)

            if not isinstance(data, list):
                raise ValueError("Expected a JSON list")

            interval = detect_interval(dataset, data)
            retrieved_ms = filename_timestamp_ms(
                timestamp_text
            )

            relative_path = path.relative_to(
                PROJECT_ROOT
            ).as_posix()

            checksum = hashlib.sha256(
                raw_bytes
            ).hexdigest()

            # Detect unexpected changes to indexed raw files.
            existing = connection.execute(
                """
                SELECT sha256
                FROM raw_files
                WHERE file_path = ?
                """,
                (relative_path,),
            ).fetchone()

            if existing and existing[0] != checksum:
                raise ValueError(
                    "Raw file changed since indexing"
                )

            connection.execute(
                """
                INSERT OR IGNORE INTO raw_files
                (
                    file_path,
                    sha256,
                    symbol,
                    dataset,
                    interval,
                    retrieved_at_ms,
                    record_count
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    relative_path,
                    checksum,
                    symbol,
                    dataset,
                    interval,
                    retrieved_ms,
                    len(data),
                ),
            )

            raw_file_id = connection.execute(
                """
                SELECT id
                FROM raw_files
                WHERE file_path = ?
                """,
                (relative_path,),
            ).fetchone()[0]

            stats["raw_files"] += 1

            # Only normalize five-minute datasets.
            if interval != "5m":

                if interval == "1m":
                    stats["one_minute_files_skipped"] += 1

                continue

            for record in data:

                try:
                    if dataset == "oi":

                        row = normalize_oi(
                            record,
                            symbol,
                        )

                        cursor = connection.execute(
                            """
                            INSERT OR IGNORE INTO oi_observations
                            (
                                symbol,
                                source_timestamp_ms,
                                bucket_end_ms,
                                oi_quantity,
                                oi_notional_quote,
                                cmc_supply,
                                raw_file_id
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                row["symbol"],
                                row["source_timestamp_ms"],
                                row["bucket_end_ms"],
                                row["oi_quantity"],
                                row["oi_notional_quote"],
                                row["cmc_supply"],
                                raw_file_id,
                            ),
                        )

                        stats["oi_inserted"] += cursor.rowcount

                    else:

                        row = normalize_kline(
                            record,
                            symbol,
                        )

                        # Don't insert unfinished candles.
                        if row["bucket_end_ms"] > retrieved_ms:
                            stats[
                                "incomplete_candles_skipped"
                            ] += 1
                            continue

                        cursor = connection.execute(
                            """
                            INSERT OR IGNORE INTO price_candles
                            (
                                symbol,
                                open_ms,
                                close_ms,
                                bucket_end_ms,
                                open_price,
                                high_price,
                                low_price,
                                close_price,
                                base_volume,
                                quote_volume,
                                trade_count,
                                taker_buy_base,
                                taker_buy_quote,
                                raw_file_id
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                row["symbol"],
                                row["open_ms"],
                                row["close_ms"],
                                row["bucket_end_ms"],
                                row["open_price"],
                                row["high_price"],
                                row["low_price"],
                                row["close_price"],
                                row["base_volume"],
                                row["quote_volume"],
                                row["trade_count"],
                                row["taker_buy_base"],
                                row["taker_buy_quote"],
                                raw_file_id,
                            ),
                        )

                        stats[
                            "candles_inserted"
                        ] += cursor.rowcount

                except (
                    ValueError,
                    KeyError,
                    TypeError,
                    IndexError,
                ) as error:

                    stats["invalid_records"] += 1

                    console.print(
                        f"[dim]Skipped {path.name}: {error}[/dim]"
                    )

        except (
            OSError,
            ValueError,
            TypeError,
        ) as error:

            console.print(
                f"[dim]File error: {path.name}: {error}[/dim]"
            )

    return stats


# ----------------------------------------
# SQLITE TERMINAL SUMMARY
# ----------------------------------------

def display_summary(connection, stats, before):
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
            delta = (
                Decimal(taker_buy_quote) * 2
                - Decimal(total_quote)
            )

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
        "[grey62]Database:[/grey62] data/market_data.sqlite3"
    )


# ----------------------------------------
# MAIN
# ----------------------------------------

def main():

    if not RAW_DIR.exists():
        console.print("No data/raw directory found.")
        return

    connection = sqlite3.connect(DB_PATH)

    try:
        connection.execute("PRAGMA foreign_keys = ON")

        connection.executescript(SCHEMA)

        # Before ingestion.
        before = database_snapshot(connection)

        # Normalize and insert.
        with connection:
            stats = load_files(connection)

        # After ingestion, show growth.
        display_summary(
            connection,
            stats,
            before,
        )

    finally:
        connection.close()


if __name__ == "__main__":
    main()
