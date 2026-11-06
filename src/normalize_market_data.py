
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


def normalize_oi(record, symbol):
    """Normalize one Binance historical OI observation."""

    if not isinstance(record, dict):
        raise ValueError("OI record must be a dictionary")

    if record["symbol"] != symbol:
        raise ValueError("OI symbol does not match source file")

    timestamp_ms = int(record["timestamp"])

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

    open_ms = int(record[0])
    close_ms = int(record[6])
    bucket_end_ms = open_ms + INTERVAL_MS

    if open_ms % INTERVAL_MS != 0:
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

    trade_count = int(record[8])

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
