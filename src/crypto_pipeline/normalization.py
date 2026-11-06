
# Import Decimal, InvalidOperation from decimal for use below.
from decimal import Decimal, InvalidOperation

# Five minutes expressed in milliseconds.
INTERVAL_MS = 5 * 60 * 1000


# Validate a numeric value and preserve its decimal text.
def decimal_text(value, field, positive=False):
    """
    Validate a numeric value and preserve its decimal text.

    Do not round or convert source values to float.
    """
    # Run this operation with the error handling and cleanup defined below.
    try:
        # Construct an exact decimal from the supplied value; store the result in number.
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        # Stop this operation with ValueError(f'Invalid {field}: {value}').
        raise ValueError(f"Invalid {field}: {value}") from error

    # Reject NaN and infinity before they can enter decimal calculations or storage.
    if not number.is_finite():
        # Stop this operation with ValueError(f'{field} must be finite').
        raise ValueError(f"{field} must be finite")

    # Reject negative values, and reject zero for fields such as prices that must be positive.
    if number < 0 or (positive and number == 0):
        # Stop this operation with ValueError(f'{field} must be positive/nonnegative').
        raise ValueError(f"{field} must be positive/nonnegative")

    # Return str(value) to the caller.
    return str(value)


# Reject booleans/floats rather than silently truncating millisecond times.
def integer_value(value, field):
    """Reject booleans/floats rather than silently truncating millisecond times."""
    # Reject booleans and floats so timestamps and trade counts cannot be silently truncated.
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        # Stop this operation with ValueError(f'{field} must be an integer').
        raise ValueError(f"{field} must be an integer")
    # Run this operation with the error handling and cleanup defined below.
    try:
        # Convert the already-selected value to an integer; store the result in number.
        number = int(value)
        # Reject values outside SQLite's signed 64-bit integer range before insertion.
        if not -(2**63) <= number < 2**63:
            # Stop this operation with ValueError(f'{field} exceeds SQLite integer range').
            raise ValueError(f"{field} exceeds SQLite integer range")
        # Return number to the caller.
        return number
    except ValueError as error:
        # Stop this operation with ValueError(f'{field} must be an integer').
        raise ValueError(f"{field} must be an integer") from error


# Normalize one Binance historical OI observation.
def normalize_oi(record, symbol):
    """Normalize one Binance historical OI observation."""

    # OI responses must be objects with named fields.
    if not isinstance(record, dict):
        # Stop this operation with ValueError('OI record must be a dictionary').
        raise ValueError("OI record must be a dictionary")

    # Refuse to attach a different contract's OI record to this source file.
    if record["symbol"] != symbol:
        # Stop this operation with ValueError('OI symbol does not match source file').
        raise ValueError("OI symbol does not match source file")

    # Validate an exact integer without silently truncating fractional values; store the result in timestamp_ms.
    timestamp_ms = integer_value(record["timestamp"], "OI timestamp")

    # Require a source observation timestamp after the Unix epoch.
    if timestamp_ms <= 0:
        # Stop this operation with ValueError('Invalid OI timestamp').
        raise ValueError("Invalid OI timestamp")

    # Read the requested optional value using its default when absent; store the result in supply.
    supply = record.get("CMCCirculatingSupply")

    # Return the normalized OI fields without rescaling source quantities or notionals.
    return {
        # Keep the exchange-native contract identifier for joins and deduplication.
        "symbol": symbol,
        # Preserve the exact observation timestamp supplied by Binance.
        "source_timestamp_ms": timestamp_ms,

        # Only assign a join key if exactly aligned.
        "bucket_end_ms": (
            timestamp_ms
            if timestamp_ms % INTERVAL_MS == 0
            else None
        ),

        # Keep reported OI quantity in native units; do not infer a multiplier from the symbol.
        "oi_quantity": decimal_text(
            record["sumOpenInterest"], "OI quantity"
        ),

        # Keep Binance's reported OI valuation, rather than recomputing it from candle prices.
        "oi_notional_quote": decimal_text(
            record["sumOpenInterestValue"], "OI notional"
        ),

        # Keep the optional CMC supply reference separate from future CoinGecko snapshots.
        "cmc_supply": (
            decimal_text(supply, "circulating supply")
            if supply is not None else None
        ),
    }


# Normalize one Binance five-minute candle.
def normalize_kline(record, symbol):
    """Normalize one Binance five-minute candle."""

    # Require the complete twelve-field Binance kline layout before reading positional values.
    if not isinstance(record, list) or len(record) != 12:
        # Stop this operation with ValueError('Expected a 12-field kline list').
        raise ValueError("Expected a 12-field kline list")

    # Validate an exact integer without silently truncating fractional values; store the result in open_ms.
    open_ms = integer_value(record[0], "open timestamp")
    # Validate an exact integer without silently truncating fractional values; store the result in close_ms.
    close_ms = integer_value(record[6], "close timestamp")
    # Calculate open_ms + INTERVAL_MS; store the result in bucket_end_ms.
    bucket_end_ms = open_ms + INTERVAL_MS

    # A valid candle must start on a nonnegative, exact five-minute boundary.
    if open_ms < 0 or open_ms % INTERVAL_MS != 0:
        # Stop this operation with ValueError('Kline opening time is not 5m-aligned').
        raise ValueError("Kline opening time is not 5m-aligned")

    # Binance's inclusive close time must be one millisecond before the exclusive period end.
    if close_ms != bucket_end_ms - 1:
        # Stop this operation with ValueError('Kline duration is not five minutes').
        raise ValueError("Kline duration is not five minutes")

    # Build a collection by selecting and transforming the specified inputs; store the result in prices.
    prices = [
        Decimal(decimal_text(record[i], f"price[{i}]", True))
        for i in range(1, 5)
    ]

    # Use prices; store the result in (opening, high, low, closing).
    opening, high, low, closing = prices

    # The reported high cannot be below any of the candle's other prices.
    if high < max(opening, closing, low):
        # Stop this operation with ValueError('Invalid candle high').
        raise ValueError("Invalid candle high")

    # The reported low cannot be above any of the candle's other prices.
    if low > min(opening, closing, high):
        # Stop this operation with ValueError('Invalid candle low').
        raise ValueError("Invalid candle low")

    # Validate the numeric field while retaining its original decimal text; store the result in base_volume.
    base_volume = decimal_text(record[5], "base volume")
    # Validate the numeric field while retaining its original decimal text; store the result in quote_volume.
    quote_volume = decimal_text(record[7], "quote volume")

    # Validate the numeric field while retaining its original decimal text; store the result in taker_base.
    taker_base = decimal_text(record[9], "taker base volume")
    # Validate the numeric field while retaining its original decimal text; store the result in taker_quote.
    taker_quote = decimal_text(record[10], "taker quote volume")

    # Taker-buy base volume is a subset of total base volume, never larger.
    if Decimal(taker_base) > Decimal(base_volume):
        # Stop this operation with ValueError('Taker-buy base exceeds total volume').
        raise ValueError("Taker-buy base exceeds total volume")

    # Taker-buy quote turnover is a subset of total quote turnover, never larger.
    if Decimal(taker_quote) > Decimal(quote_volume):
        # Stop this operation with ValueError('Taker-buy quote exceeds total volume').
        raise ValueError("Taker-buy quote exceeds total volume")

    # Validate an exact integer without silently truncating fractional values; store the result in trade_count.
    trade_count = integer_value(record[8], "trade count")

    # A candle cannot contain a negative number of trades.
    if trade_count < 0:
        # Stop this operation with ValueError('Negative trade count').
        raise ValueError("Negative trade count")

    # Return the validated candle fields with exact source decimals and an exclusive-end join key.
    return {
        # Keep the exchange-native contract identifier for joins and deduplication.
        "symbol": symbol,
        # Persist the candle's inclusive opening timestamp in Unix milliseconds.
        "open_ms": open_ms,
        # Persist Binance's inclusive close timestamp, one millisecond before period end.
        "close_ms": close_ms,
        # Use the exclusive period end to align a completed candle with an OI observation.
        "bucket_end_ms": bucket_end_ms,

        # Preserve the original opening price text, in quote units per native base unit.
        "open_price": str(record[1]),
        # Preserve the original highest traded price text.
        "high_price": str(record[2]),
        # Preserve the original lowest traded price text.
        "low_price": str(record[3]),
        # Preserve the original closing price text.
        "close_price": str(record[4]),

        # Keep total traded volume in native base units, not quote notional.
        "base_volume": base_volume,
        # Keep total traded quote-asset turnover; do not implicitly convert USDT to USD.
        "quote_volume": quote_volume,
        # Keep the validated integer count of trades during this candle.
        "trade_count": trade_count,
        # Keep the base-unit portion traded by aggressive buyers.
        "taker_buy_base": taker_base,
        # Keep the quote-unit portion traded by aggressive buyers for delta calculations.
        "taker_buy_quote": taker_quote,
    }
