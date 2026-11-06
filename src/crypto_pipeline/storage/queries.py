from ..config import SYMBOLS

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


