
from decimal import Decimal, InvalidOperation

# Five minutes expressed in milliseconds.
INTERVAL_MS = 5 * 60 * 1000


def decimal_text(value, field, positive=False):
    """
    Validate a numeric value and preserve its decimal text.

    Do not round or convert source values to float.
    """
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"Invalid {field}: {value}") from error

    if not number.is_finite():
        raise ValueError(f"{field} must be finite")

    if number < 0 or (positive and number == 0):
        raise ValueError(f"{field} must be positive/nonnegative")

    return str(value)


def integer_value(value, field):
    """Reject booleans/floats rather than silently truncating millisecond times."""
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError(f"{field} must be an integer")
    try:
        number = int(value)
        if not -(2**63) <= number < 2**63:
            raise ValueError(f"{field} exceeds SQLite integer range")
        return number
    except ValueError as error:
        raise ValueError(f"{field} must be an integer") from error


def normalize_oi(record, symbol):
    """Normalize one Binance historical OI observation."""

    if not isinstance(record, dict):
        raise ValueError("OI record must be a dictionary")

    if record["symbol"] != symbol:
        raise ValueError("OI symbol does not match source file")

    timestamp_ms = integer_value(record["timestamp"], "OI timestamp")

    if timestamp_ms <= 0:
        raise ValueError("Invalid OI timestamp")

    supply = record.get("CMCCirculatingSupply")

    return {
        "symbol": symbol,
        "source_timestamp_ms": timestamp_ms,

        # Only assign a join key if exactly aligned.
        "bucket_end_ms": (
            timestamp_ms
            if timestamp_ms % INTERVAL_MS == 0
            else None
        ),

        "oi_quantity": decimal_text(
            record["sumOpenInterest"], "OI quantity"
        ),

        "oi_notional_quote": decimal_text(
            record["sumOpenInterestValue"], "OI notional"
        ),

        "cmc_supply": (
            decimal_text(supply, "circulating supply")
            if supply is not None else None
        ),
    }


def normalize_kline(record, symbol):
    """Normalize one Binance five-minute candle."""

    if not isinstance(record, list) or len(record) != 12:
        raise ValueError("Expected a 12-field kline list")

    open_ms = integer_value(record[0], "open timestamp")
    close_ms = integer_value(record[6], "close timestamp")
    bucket_end_ms = open_ms + INTERVAL_MS

    if open_ms < 0 or open_ms % INTERVAL_MS != 0:
        raise ValueError("Kline opening time is not 5m-aligned")

    if close_ms != bucket_end_ms - 1:
        raise ValueError("Kline duration is not five minutes")

    prices = [
        Decimal(decimal_text(record[i], f"price[{i}]", True))
        for i in range(1, 5)
    ]

    opening, high, low, closing = prices

    if high < max(opening, closing, low):
        raise ValueError("Invalid candle high")

    if low > min(opening, closing, high):
        raise ValueError("Invalid candle low")

    base_volume = decimal_text(record[5], "base volume")
    quote_volume = decimal_text(record[7], "quote volume")

    taker_base = decimal_text(record[9], "taker base volume")
    taker_quote = decimal_text(record[10], "taker quote volume")

    if Decimal(taker_base) > Decimal(base_volume):
        raise ValueError("Taker-buy base exceeds total volume")

    if Decimal(taker_quote) > Decimal(quote_volume):
        raise ValueError("Taker-buy quote exceeds total volume")

    trade_count = integer_value(record[8], "trade count")

    if trade_count < 0:
        raise ValueError("Negative trade count")

    return {
        "symbol": symbol,
        "open_ms": open_ms,
        "close_ms": close_ms,
        "bucket_end_ms": bucket_end_ms,

        "open_price": str(record[1]),
        "high_price": str(record[2]),
        "low_price": str(record[3]),
        "close_price": str(record[4]),

        "base_volume": base_volume,
        "quote_volume": quote_volume,
        "trade_count": trade_count,
        "taker_buy_base": taker_base,
        "taker_buy_quote": taker_quote,
    }
