
# Import datetime, timezone, timedelta from datetime for use below.
from datetime import datetime, timezone, timedelta
# Import Decimal from decimal for use below.
from decimal import Decimal
# Import Path from pathlib for use below.
from pathlib import Path

# Import Console from rich.console for use below.
from rich.console import Console
# Import Text from rich.text for use below.
from rich.text import Text
# Import Table from rich.table for use below.
from rich.table import Table


# ----------------------------------------
# DISPLAY SETTINGS
# ----------------------------------------

# Create the Rich console used for terminal presentation; store the result in console.
console = Console(highlight=False)

# Use the explicit text '#8EAABD'; store the result in ACCENT.
ACCENT = "#8EAABD"
# Use the explicit text 'grey62'; store the result in LABEL_COLOR.
LABEL_COLOR = "grey62"
# Use the explicit text '#72D9A4'; store the result in GROWTH_COLOR.
GROWTH_COLOR = "#72D9A4"


# ----------------------------------------
# NUMBER AND DATE FORMATTING
# ----------------------------------------

# Format numbers for display without changing raw data.
def format_number(value, decimals=3):
    """Format numbers for display without changing raw data."""

    # Construct an exact decimal from the supplied value; store the result in number.
    number = Decimal(str(value))
    # Build the text using the current field values; store the result in result.
    result = f"{number:,.{decimals}f}"

    # Enter this branch only when '.' in result.
    if "." in result:
        # Return result.rstrip('0').rstrip('.') to the caller.
        return result.rstrip("0").rstrip(".")

    # Return result to the caller.
    return result


# Display additional precision for low-priced assets.
def format_price(value):
    """Display additional precision for low-priced assets."""

    # Construct an exact decimal from the supplied value; store the result in price.
    price = Decimal(str(value))
    # Choose the value according to abs(price) < Decimal('0.01'); store the result in decimals.
    decimals = 8 if abs(price) < Decimal("0.01") else 2

    # Return format_number(price, decimals) to the caller.
    return format_number(price, decimals)


# Convert Unix milliseconds into readable UTC.
def format_timestamp(milliseconds):
    """Convert Unix milliseconds into readable UTC."""

    # Add the exact millisecond offset to the UTC Unix epoch for display.
    dt = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=int(milliseconds))

    # Return dt.strftime('%Y-%m-%d %H:%M:%S UTC') to the caller.
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


# ----------------------------------------
# BINANCE FIELD PRESENTATION
# ----------------------------------------

# Map Binance OI fields to readable display values.
def format_oi(record):
    """Map Binance OI fields to readable display values."""

    # Read the requested optional value using its default when absent; store the result in supply.
    supply = record.get("CMCCirculatingSupply")

    # Return labeled OI fields for terminal presentation; the stored data remains unchanged.
    return [
        ("Symbol", record["symbol"]),
        (
            "Observation",
            format_timestamp(record["timestamp"]),
        ),
        (
            "OI quantity",
            format_number(record["sumOpenInterest"]),
        ),
        (
            "OI notional",
            format_number(
                record["sumOpenInterestValue"], 2
            ) + " USDT",
        ),
        (
            "CMC supply reference",
            format_number(supply, 2)
            if supply is not None else "N/A",
        ),
    ]


# Map Binance's 12 kline positions to readable fields.
def format_kline(record):
    """Map Binance's 12 kline positions to readable fields."""

    # Enter this branch only when len(record) != 12.
    if len(record) != 12:
        # Stop this operation with ValueError(f'Expected 12 kline fields, received {len(record)}').
        raise ValueError(
            f"Expected 12 kline fields, received {len(record)}"
        )

    # Return readable labels for all twelve Binance candle fields.
    return [
        ("Open time", format_timestamp(record[0])),
        ("Open price", format_price(record[1])),
        ("High price", format_price(record[2])),
        ("Low price", format_price(record[3])),
        ("Close price", format_price(record[4])),
        ("Base volume", format_number(record[5])),
        ("Close time", format_timestamp(record[6])),
        (
            "Quote volume",
            format_number(record[7], 2) + " USDT",
        ),
        ("Trades", str(record[8])),
        (
            "Taker-buy base volume",
            format_number(record[9]),
        ),
        (
            "Taker-buy quote volume",
            format_number(record[10], 2) + " USDT",
        ),
        ("Ignore", str(record[11])),
    ]


# ----------------------------------------
# REUSABLE TERMINAL FORMATTING
# ----------------------------------------

