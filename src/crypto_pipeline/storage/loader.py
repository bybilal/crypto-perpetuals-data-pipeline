import hashlib
import json
import re
import sqlite3
from ..normalization import normalize_oi, normalize_kline
from ..reporting import console
from ..summary import display_summary
from ..time_utils import filename_timestamp_ms, utc_label, detect_interval
from ..config import PROJECT_ROOT, RAW_DIR, DB_PATH, SYMBOLS
from .schema import SCHEMA
from .queries import database_snapshot
FILENAME_PATTERN = re.compile(r"^(BTCUSDT|1000PEPEUSDT)_(oi|klines)_(\d{8}T\d{6}(?:\d{6})?Z)\.json$")

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


def main():

    if not RAW_DIR.exists():
        console.print("No data/raw directory found.")
        return

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
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
            DB_PATH.relative_to(PROJECT_ROOT) if DB_PATH.is_relative_to(PROJECT_ROOT) else DB_PATH,
        )

    finally:
        connection.close()


if __name__ == "__main__":
    main()
