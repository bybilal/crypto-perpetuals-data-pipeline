# Import hashlib for use below.
import hashlib
# Import json for use below.
import json
# Import re for use below.
import re
# Import sqlite3 for use below.
import sqlite3
# Import normalize_oi, normalize_kline from ..normalization for use below.
from ..normalization import normalize_oi, normalize_kline
# Import console from ..reporting for use below.
from ..reporting import console
# Import display_summary from ..summary for use below.
from ..summary import display_summary
# Import filename_timestamp_ms, utc_label, detect_interval from ..time_utils for use below.
from ..time_utils import filename_timestamp_ms, utc_label, detect_interval
# Import PROJECT_ROOT, RAW_DIR, DB_PATH, SYMBOLS from ..config for use below.
from ..config import PROJECT_ROOT, RAW_DIR, DB_PATH, SYMBOLS
# Import SCHEMA from .schema for use below.
from .schema import SCHEMA
# Import insert_observation from .records for use below.
from .records import insert_observation
# Import apply_migrations from .migrations for use below.
from .migrations import apply_migrations
# Import load_metadata from .metadata for use below.
from .metadata import load_metadata
# Import emit from ..events for use below.
from ..events import emit
# Import database_snapshot from .queries for use below.
from .queries import database_snapshot
# Accept only configured contracts, supported datasets, and UTC capture filenames.
FILENAME_PATTERN = re.compile(r"^(BTCUSDT|1000PEPEUSDT)_(oi|klines)_(\d{8}T\d{6}(?:\d{6})?Z)\.json$")

# Normalize saved JSON and insert valid 5m observations.
def load_files(connection, paths=None):
    """Normalize saved JSON and insert valid 5m observations."""

    # Build the named fields used by this operation; store the result in stats.
    stats = {
        "raw_files": 0,
        "oi_inserted": 0,
        "candles_inserted": 0,
        "one_minute_files_skipped": 0,
        "incomplete_candles_skipped": 0,
        "invalid_records": 0,
        "file_errors": 0,
    }

    # Process each path from sorted(RAW_DIR.glob('*.json')).
    for path in sorted(RAW_DIR.glob("*.json") if paths is None else paths):

        # Match the filename against the supported contract/dataset timestamp pattern; store the result in match.
        match = FILENAME_PATTERN.match(path.name)

        # Ignore files outside the supported contract/dataset naming scheme.
        if not match:
            # Skip the remaining work for this item and continue the enclosing loop.
            continue

        # Extract the contract, dataset and timestamp from the matched filename; store the result in (symbol, dataset, timestamp_text).
        symbol, dataset, timestamp_text = match.groups()

        # Run this operation with the error handling and cleanup defined below.
        try:
            # Read the file exactly as stored, before JSON parsing or normalization; store the result in raw_bytes.
            raw_bytes = path.read_bytes()
            # Parse the JSON payload into Python objects; store the result in data.
            data = json.loads(raw_bytes)

            # Enter this branch only when not isinstance(data, list).
            if not isinstance(data, list):
                # Stop this operation with ValueError('Expected a JSON list').
                raise ValueError("Expected a JSON list")

            # Identify five-minute versus legacy one-minute candle data; store the result in interval.
            interval = detect_interval(dataset, data)
            # Convert the UTC filename timestamp to integer Unix milliseconds; store the result in retrieved_ms.
            retrieved_ms = filename_timestamp_ms(
                timestamp_text
            )

            # Choose the value according to path.is_relative_to(PROJECT_ROOT); store the result in relative_path.
            relative_path = path.relative_to(PROJECT_ROOT).as_posix() if path.is_relative_to(PROJECT_ROOT) else str(path.resolve())

            # Represent the content fingerprint as a hexadecimal string; store the result in checksum.
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

            # Enter this branch only when existing and existing[0] != checksum.
            if existing and existing[0] != checksum:
                # Stop this operation with ValueError('Raw file changed since indexing').
                raise ValueError(
                    "Raw file changed since indexing"
                )

            # Insert a new row while leaving an existing unique-key match unchanged.
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

            # Retrieve the indexed raw file ID for observation provenance links.
            raw_file_id = connection.execute(
                """
                SELECT id
                FROM raw_files
                WHERE file_path = ?
                """,
                (relative_path,),
            ).fetchone()[0]

            # Update stats['raw_files'] using 1 for this step.
            stats["raw_files"] += 1

            # Only normalize five-minute datasets.
            if interval != "5m":

                # Enter this branch only when interval == '1m'.
                if interval == "1m":
                    # Update stats['one_minute_files_skipped'] using 1 for this step.
                    stats["one_minute_files_skipped"] += 1
                elif data:
                    stats["file_errors"] += 1
                    emit("load", "file_error", file=path.name, error="Unsupported or malformed candle interval")

                # Skip the remaining work for this item and continue the enclosing loop.
                continue

            # Process each record from data.
            for record in data:

                # Run this operation with the error handling and cleanup defined below.
                try:
                    # Enter this branch only when dataset == 'oi'.
                    if dataset == "oi":

                        # Validate OI fields and preserve native decimal units and exact time alignment; store the result in row.
                        row = normalize_oi(
                            record,
                            symbol,
                        )

                        # Insert the normalized record using the table's fixed column definitions; store the result in inserted.
                        inserted = insert_observation(connection, "oi_observations", row, raw_file_id)

                        # Update stats['oi_inserted'] using inserted for this step.
                        stats["oi_inserted"] += inserted

                    else:

                        # Validate five-minute candle boundaries, prices and volume constraints; store the result in row.
                        row = normalize_kline(
                            record,
                            symbol,
                        )

                        # Don't insert unfinished candles.
                        if row["bucket_end_ms"] > retrieved_ms:
                            # Update stats['incomplete_candles_skipped'] using 1 for this step.
                            stats[
                                "incomplete_candles_skipped"
                            ] += 1
                            # Skip the remaining work for this item and continue the enclosing loop.
                            continue

                        # Insert the normalized record using the table's fixed column definitions; store the result in inserted.
                        inserted = insert_observation(connection, "price_candles", row, raw_file_id)

                        # Update stats['candles_inserted'] using inserted for this step.
                        stats[
                            "candles_inserted"
                        ] += inserted

                except (
                    ValueError,
                    KeyError,
                    TypeError,
                    IndexError,
                ) as error:

                    # Update stats['invalid_records'] using 1 for this step.
                    stats["invalid_records"] += 1
                    # Write this stage event to the active run logs without printing to the terminal.
                    emit("normalize", "invalid_record", file=path.name, error=str(error))

                    # Write the formatted output to the terminal.
                    console.print(
                        f"[dim]Skipped {path.name}: {error}[/dim]"
                    )

        except (
            OSError,
            ValueError,
            TypeError,
        ) as error:

            # Update stats['file_errors'] using 1 for this step.
            stats["file_errors"] += 1
            # Write this stage event to the active run logs without printing to the terminal.
            emit("load", "file_error", file=path.name, error=str(error))
            # Write the formatted output to the terminal.
            console.print(
                f"[dim]File error: {path.name}: {error}[/dim]"
            )

    # Return stats to the caller.
    return stats


# Define main with the inputs listed below.
def main():

    # Stop when the configured raw-data directory does not exist.
    if not RAW_DIR.exists():
        # Write the formatted output to the terminal.
        console.print("No data/raw directory found.")
        # Stop this function without returning a result.
        return

    # Create the needed output directory, including missing parents.
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Open a SQLite connection using the specified database path; store the result in connection.
    connection = sqlite3.connect(DB_PATH)

    # Run this operation with the error handling and cleanup defined below.
    try:
        # Enable SQLite foreign-key validation for this connection.
        connection.execute("PRAGMA foreign_keys = ON")

        # Apply any required schema upgrades, backing up an existing database first.
        apply_migrations(connection, DB_PATH)

        # Before ingestion.
        before = database_snapshot(connection)

        # Normalize and insert.
        with connection:
            # Import saved exchangeInfo specifications and their provenance.
            load_metadata(connection, RAW_DIR, PROJECT_ROOT)
            # Validate saved raw files and insert previously unseen observations; store the result in stats.
            stats = load_files(connection)
        # Write this stage event to the active run logs without printing to the terminal.
        emit("load", "completed", counts=stats, totals=database_snapshot(connection))

        # After ingestion, show growth.
        display_summary(
            connection,
            stats,
            before,
            DB_PATH.relative_to(PROJECT_ROOT) if DB_PATH.is_relative_to(PROJECT_ROOT) else DB_PATH,
        )

        # Return stats to the caller.
        return stats

    finally:
        # Close the open resource and release its operating-system handle.
        connection.close()


# Run this entry point only when the file is executed directly.
if __name__ == "__main__":
    # Invoke the standalone loader when this module is executed directly.
    main()
