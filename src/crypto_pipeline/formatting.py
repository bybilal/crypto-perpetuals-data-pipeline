
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path

from rich.console import Console
from rich.text import Text
from rich.table import Table


# ----------------------------------------
# DISPLAY SETTINGS
# ----------------------------------------

console = Console(highlight=False)

ACCENT = "#8EAABD"
LABEL_COLOR = "grey62"
GROWTH_COLOR = "#72D9A4"


# ----------------------------------------
# NUMBER AND DATE FORMATTING
# ----------------------------------------

def format_number(value, decimals=3):
    """Format numbers for display without changing raw data."""

    number = Decimal(str(value))
    result = f"{number:,.{decimals}f}"

    if "." in result:
        return result.rstrip("0").rstrip(".")

    return result


def format_price(value):
    """Display additional precision for low-priced assets."""

    price = Decimal(str(value))
    decimals = 8 if abs(price) < Decimal("0.01") else 2

    return format_number(price, decimals)


def format_timestamp(milliseconds):
    """Convert Unix milliseconds into readable UTC."""

    dt = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=int(milliseconds))

    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


# ----------------------------------------
# BINANCE FIELD PRESENTATION
# ----------------------------------------

def format_oi(record):
    """Map Binance OI fields to readable display values."""

    supply = record.get("CMCCirculatingSupply")

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


def format_kline(record):
    """Map Binance's 12 kline positions to readable fields."""

    if len(record) != 12:
        raise ValueError(
            f"Expected 12 kline fields, received {len(record)}"
        )

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

