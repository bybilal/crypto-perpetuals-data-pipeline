# Import SYMBOLS from ..config for use below.
from ..config import SYMBOLS

# Capture database counts before or after ingestion.
def database_snapshot(connection):
    """
    Capture database counts before or after ingestion.

    Used to calculate per-run growth indicators.
    """

    # Build the named fields used by this operation; store the result in snapshot.
    snapshot = {
        "raw_files": connection.execute(
            "SELECT COUNT(*) FROM raw_files"
        ).fetchone()[0],
        "contracts": {},
    }

    # Process each symbol from SYMBOLS.
    for symbol in SYMBOLS:

        # Count OI observations for this contract.
        oi = connection.execute(
            """
            SELECT COUNT(*)
            FROM oi_observations
            WHERE symbol = ?
            """,
            (symbol,),
        ).fetchone()[0]

        # Count stored candles for this contract.
        candles = connection.execute(
            """
            SELECT COUNT(*)
            FROM price_candles
            WHERE symbol = ?
            """,
            (symbol,),
        ).fetchone()[0]

        # Count only OI/candle pairs sharing both contract symbol and period-end timestamp.
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

        # Build the named fields used by this operation; store the result in snapshot['contracts'][symbol].
        snapshot["contracts"][symbol] = {
            "oi": oi,
            "candles": candles,
            "aligned": aligned,
        }

    # Return snapshot to the caller.
    return snapshot


