"""Read-only coverage for the most recent hour of mature five-minute boundaries."""
# Explicitly close read-only connections when the report is complete.
from contextlib import closing
# Read wall-clock time in integer nanoseconds before converting to milliseconds.
from time import time_ns
import sqlite3
from .config import SYMBOLS
from .normalization import INTERVAL_MS
from .time_utils import utc_label
from .events import emit
from .reporting import console


def recent_coverage(db_path, now_ms=None):
    """Report missing OI/candle timestamps independently, with one minute of publication grace."""
    # A supplied clock makes boundary tests deterministic.
    if now_ms is None:
        now_ms = time_ns() // 1_000_000
    # Exclude the latest boundary until its one-minute publication grace has elapsed.
    end_ms = ((now_ms - 60_000) // INTERVAL_MS) * INTERVAL_MS
    # Twelve consecutive period ends represent one hour of five-minute windows.
    start_ms = end_ms - 11 * INTERVAL_MS
    expected = set(range(start_ms, end_ms + 1, INTERVAL_MS))
    rows = []
    # mode=ro fails for a missing database instead of silently creating an empty file.
    with closing(sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        # All streams must be observed from the same SQLite read snapshot.
        connection.execute("BEGIN")
        for symbol in SYMBOLS:
            row = {"symbol": symbol}
            # Fixed table names keep query identifiers separate from user-supplied values.
            for key, table in (("oi", "oi_observations"), ("candles", "price_candles")):
                found = {record[0] for record in connection.execute(
                    f"SELECT bucket_end_ms FROM {table} WHERE symbol=? AND bucket_end_ms BETWEEN ? AND ?",
                    (symbol, start_ms, end_ms),
                )}
                # An absent row is reported without assuming why the source omitted it.
                row[key] = len(expected & found)
                row[key + "_missing_ms"] = sorted(expected - found)
                # Age labels are diagnostic thresholds, not proof of the cause of missing data.
                row[key + "_recent_missing_ms"] = [t for t in row[key + "_missing_ms"] if now_ms - t <= 600_000]
                row[key + "_older_missing_ms"] = [t for t in row[key + "_missing_ms"] if now_ms - t > 600_000]
                row[key + "_latest_ms"] = connection.execute(
                    f"SELECT MAX(bucket_end_ms) FROM {table} WHERE symbol=?", (symbol,)
                ).fetchone()[0]
            rows.append(row)
    return {"first_end_ms": start_ms, "last_end_ms": end_ms, "expected": 12, "contracts": rows}


def display_recent_coverage(db_path):
    """Show compact coverage in Rich and retain exact absent timestamps in JSONL."""
    report = recent_coverage(db_path)
    console.print("[grey62]Recent coverage / 1h / period ends (UTC)[/grey62]")
    console.print(f"  {utc_label(report['first_end_ms'])} — {utc_label(report['last_end_ms'])}")
    for row in report["contracts"]:
        console.print(f"  {row['symbol']:<14} OI {row['oi']:>2}/12   Candles {row['candles']:>2}/12")
        # Missing source periods may be delayed, unavailable or outside our captured history.
        # Preserve the familiar summary and add details only when missing data exists.
        recent = len(row["oi_recent_missing_ms"]) + len(row["candles_recent_missing_ms"])
        older = len(row["oi_older_missing_ms"]) + len(row["candles_older_missing_ms"])
        if recent or older:
            console.print(f"    [grey62]Missing observations: {recent} recent (≤10m), {older} older unresolved[/grey62]")
    emit("coverage", "checked", **report)
    console.print()
