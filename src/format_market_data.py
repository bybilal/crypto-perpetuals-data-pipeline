
from datetime import datetime, timezone
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

    dt = datetime.fromtimestamp(
        int(milliseconds) / 1000,
        tz=timezone.utc,
    )

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

def display_heading(symbol, dataset, interval, count):
    """Display a minimal heading with a muted accent."""

    heading = Text()

    heading.append(symbol, style=ACCENT)
    heading.append(f" / {dataset.upper()} / {interval}")
    heading.append(
        f"  ({count} records)",
        style=LABEL_COLOR,
    )

    console.print()
    console.print(heading)
    console.print()


def display_fields(rows):
    """Display aligned labels and values without a table."""

    label_width = max(len(label) for label, _ in rows)

    for label, value in rows:
        line = Text()

        line.append(
            f"  {label:<{label_width}}  ",
            style=LABEL_COLOR,
        )

        line.append(str(value))

        console.print(line)


def display_saved_path(path, project_root):
    """Display the raw file's location."""

    relative_path = Path(path).relative_to(project_root)

    line = Text()

    line.append("  Saved: ", style=LABEL_COLOR)
    line.append(str(relative_path), style="dim")

    console.print()
    console.print(line)


def display_error(symbol, dataset, error_type, message):
    """Display errors using the same minimal terminal style."""

    line = Text()

    line.append(f"{symbol} / {dataset}: ", style=ACCENT)
    line.append(f"{error_type}: {message}")

    console.print()
    console.print(line)


# ----------------------------------------
# MARKET DATA INSPECTION
# ----------------------------------------

def display_response(
    symbol,
    dataset,
    interval,
    data,
    path,
    project_root,
):
    """Display a parsed API response without changing it."""

    display_heading(
        symbol,
        dataset,
        interval,
        len(data),
    )

    if data:
        first_record = data[0]

        if dataset == "oi":
            rows = format_oi(first_record)

        elif dataset == "klines":
            rows = format_kline(first_record)

        else:
            raise ValueError(f"Unknown dataset: {dataset}")

        display_fields(rows)

    else:
        console.print("  No records returned.")

    display_saved_path(path, project_root)


# ----------------------------------------
# CONTRACT METADATA
# ----------------------------------------

def display_contract_metadata(contracts, path, project_root):
    """Display selected Binance contract specifications."""

    for contract in contracts:

        filters = {
            item["filterType"]: item
            for item in contract.get("filters", [])
        }

        price_filter = filters.get("PRICE_FILTER", {})
        lot_filter = filters.get("LOT_SIZE", {})

        heading = Text()

        heading.append(contract["symbol"], style=ACCENT)
        heading.append(" / CONTRACT METADATA")

        console.print()
        console.print(heading)
        console.print()

        rows = [
            ("Base asset", contract.get("baseAsset", "N/A")),
            ("Quote asset", contract.get("quoteAsset", "N/A")),
            ("Margin asset", contract.get("marginAsset", "N/A")),
            (
                "Contract type",
                contract.get("contractType", "N/A"),
            ),
            (
                "Trading status",
                contract.get("status", "N/A"),
            ),
            (
                "Price tick size",
                price_filter.get("tickSize", "N/A"),
            ),
            (
                "Quantity step size",
                lot_filter.get("stepSize", "N/A"),
            ),
        ]

        display_fields(rows)

    display_saved_path(path, project_root)


# ----------------------------------------
# GROWTH INDICATORS
# ----------------------------------------

def count_with_growth(total, growth=0):
    """Append a pastel-green +N when a count increases."""

    result = Text(str(total))

    if growth > 0:
        result.append(
            f"  +{growth}",
            style=GROWTH_COLOR,
        )

    return result


def display_metric(label, value, growth=0):
    """Display an aligned metric with optional growth."""

    line = Text()

    line.append(
        f"  {label:<29} ",
        style=LABEL_COLOR,
    )

    line.append_text(
        count_with_growth(value, growth)
    )

    console.print(line)


# ----------------------------------------
# SQLITE CONTRACT SUMMARY
# ----------------------------------------

def display_market_summary(rows):
    """Display a borderless table with growth indicators."""

    table = Table(
        box=None,
        show_edge=False,
        show_lines=False,
        pad_edge=False,
        padding=(0, 2),
        header_style=LABEL_COLOR,
    )

    table.add_column("Contract", style=ACCENT)
    table.add_column("OI", justify="right")
    table.add_column("Candles", justify="right")
    table.add_column("Aligned", justify="right")
    table.add_column("Latest (UTC)")
    table.add_column(
        "Quote Δ (USDT)",
        justify="right",
    )

    for row in rows:
        table.add_row(
            row["symbol"],
            count_with_growth(
                row["oi_count"],
                row.get("oi_added", 0),
            ),
            count_with_growth(
                row["candle_count"],
                row.get("candles_added", 0),
            ),
            count_with_growth(
                row["matched_count"],
                row.get("matched_added", 0),
            ),
            row["latest"],
            row["delta"],
        )

    console.print(table)
