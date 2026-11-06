# Import * from .formatting for use below.
from .formatting import *
# Import emit from .events for use below.
from .events import emit

# Display a minimal heading with a muted accent.
def display_heading(symbol, dataset, interval, count):
    """Display a minimal heading with a muted accent."""

    # Create a Rich text object that can carry styled spans; store the result in heading.
    heading = Text()

    # Add this item to the accumulating list.
    heading.append(symbol, style=ACCENT)
    # Add this item to the accumulating list.
    heading.append(f" / {dataset.upper()} / {interval}")
    # Add this item to the accumulating list.
    heading.append(
        f"  ({count} records)",
        style=LABEL_COLOR,
    )

    # Write the formatted output to the terminal.
    console.print()
    # Write the formatted output to the terminal.
    console.print(heading)
    # Write the formatted output to the terminal.
    console.print()


# Display aligned labels and values without a table.
def display_fields(rows):
    """Display aligned labels and values without a table."""

    # Choose the largest of the supplied values; store the result in label_width.
    label_width = max(len(label) for label, _ in rows)

    # Process each (label, value) from rows.
    for label, value in rows:
        # Create a Rich text object that can carry styled spans; store the result in line.
        line = Text()

        # Add this item to the accumulating list.
        line.append(
            f"  {label:<{label_width}}  ",
            style=LABEL_COLOR,
        )

        # Add this item to the accumulating list.
        line.append(str(value))

        # Write the formatted output to the terminal.
        console.print(line)


# Display the raw file's location.
def display_saved_path(path, project_root):
    """Display the raw file's location."""

    # Show the saved file relative to the repository so the terminal label stays compact.
    relative_path = Path(path).resolve()
    # External raw-directory overrides need an absolute display label.
    if relative_path.is_relative_to(Path(project_root).resolve()):
        relative_path = relative_path.relative_to(Path(project_root).resolve())

    # Create a Rich text object that can carry styled spans; store the result in line.
    line = Text()

    # Add this item to the accumulating list.
    line.append("  Saved: ", style=LABEL_COLOR)
    # Add this item to the accumulating list.
    line.append(str(relative_path), style="dim")

    # Write the formatted output to the terminal.
    console.print()
    # Write the formatted output to the terminal.
    console.print(line)


# Display errors using the same minimal terminal style.
def display_error(symbol, dataset, error_type, message):
    """Display errors using the same minimal terminal style."""

    # Write this stage event to the active run logs without printing to the terminal.
    emit("fetch", "request_error", symbol=symbol, dataset=dataset, error_type=error_type, error=message)
    # Create a Rich text object that can carry styled spans; store the result in line.
    line = Text()

    # Add this item to the accumulating list.
    line.append(f"{symbol} / {dataset}: ", style=ACCENT)
    # Add this item to the accumulating list.
    line.append(f"{error_type}: {message}")

    # Write the formatted output to the terminal.
    console.print()
    # Write the formatted output to the terminal.
    console.print(line)


# ----------------------------------------
# MARKET DATA INSPECTION
# ----------------------------------------

# Display a parsed API response without changing it.
def display_response(
    symbol,
    dataset,
    interval,
    data,
    path,
    project_root,
):
    """Display a parsed API response without changing it."""

    # Print the contract, dataset, interval and response record count.
    display_heading(
        symbol,
        dataset,
        interval,
        len(data),
    )

    # Enter this branch only when data.
    if data:
        # Read data[0] from the source data; store the result in first_record.
        first_record = data[0]

        # Enter this branch only when dataset == 'oi'.
        if dataset == "oi":
            # Map OI response fields to human-readable labels and display values; store the result in rows.
            rows = format_oi(first_record)

        # Enter this branch only when dataset == 'klines'.
        elif dataset == "klines":
            # Map the twelve candle fields to human-readable labels and display values; store the result in rows.
            rows = format_kline(first_record)

        else:
            # Stop this operation with ValueError(f'Unknown dataset: {dataset}').
            raise ValueError(f"Unknown dataset: {dataset}")

        # Render each field label beside its formatted value.
        display_fields(rows)

    else:
        # Write the formatted output to the terminal.
        console.print("  No records returned.")

    # Show where the unmodified API response was saved.
    display_saved_path(path, project_root)


# ----------------------------------------
# CONTRACT METADATA
# ----------------------------------------

# Display selected Binance contract specifications.
def display_contract_metadata(contracts, path, project_root):
    """Display selected Binance contract specifications."""

    # Process each contract from contracts.
    for contract in contracts:

        # Build a collection by selecting and transforming the specified inputs; store the result in filters.
        filters = {
            item["filterType"]: item
            for item in contract.get("filters", [])
        }

        # Read the requested optional value using its default when absent; store the result in price_filter.
        price_filter = filters.get("PRICE_FILTER", {})
        # Read the requested optional value using its default when absent; store the result in lot_filter.
        lot_filter = filters.get("LOT_SIZE", {})

        # Create a Rich text object that can carry styled spans; store the result in heading.
        heading = Text()

        # Add this item to the accumulating list.
        heading.append(contract["symbol"], style=ACCENT)
        # Add this item to the accumulating list.
        heading.append(" / CONTRACT METADATA")

        # Write the formatted output to the terminal.
        console.print()
        # Write the formatted output to the terminal.
        console.print(heading)
        # Write the formatted output to the terminal.
        console.print()

        # Build the ordered collection used by this operation; store the result in rows.
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

        # Render each field label beside its formatted value.
        display_fields(rows)

    # Show where the unmodified API response was saved.
    display_saved_path(path, project_root)


# ----------------------------------------
# GROWTH INDICATORS
# ----------------------------------------

# Append a pastel-green +N when a count increases.
def count_with_growth(total, growth=0):
    """Append a pastel-green +N when a count increases."""

    # Create a Rich text object that can carry styled spans; store the result in result.
    result = Text(str(total))

    # Add the pastel-green suffix only when this count actually increased.
    if growth > 0:
        # Add this item to the accumulating list.
        result.append(
            f"  +{growth}",
            style=GROWTH_COLOR,
        )

    # Return result to the caller.
    return result


# Display an aligned metric with optional growth.
def display_metric(label, value, growth=0):
    """Display an aligned metric with optional growth."""

    # Create a Rich text object that can carry styled spans; store the result in line.
    line = Text()

    # Add this item to the accumulating list.
    line.append(
        f"  {label:<29} ",
        style=LABEL_COLOR,
    )

    # Append styled Rich text without dropping its color spans.
    line.append_text(
        count_with_growth(value, growth)
    )

    # Write the formatted output to the terminal.
    console.print(line)


# ----------------------------------------
# SQLITE CONTRACT SUMMARY
# ----------------------------------------

# Display a borderless table with growth indicators.
def display_market_summary(rows):
    """Display a borderless table with growth indicators."""

    # Create the minimalist Rich table with its configured layout; store the result in table.
    table = Table(
        box=None,
        show_edge=False,
        show_lines=False,
        pad_edge=False,
        padding=(0, 2),
        header_style=LABEL_COLOR,
    )

    # Define a table column and its alignment or styling.
    table.add_column("Contract", style=ACCENT)
    # Define a table column and its alignment or styling.
    table.add_column("OI", justify="right")
    # Define a table column and its alignment or styling.
    table.add_column("Candles", justify="right")
    # Define a table column and its alignment or styling.
    table.add_column("Aligned", justify="right")
    # Define a table column and its alignment or styling.
    table.add_column("Latest (UTC)")
    # Define a table column and its alignment or styling.
    table.add_column(
        "Quote Δ (USDT)",
        justify="right",
    )

    # Process each row from rows.
    for row in rows:
        # Add this contract's formatted values to the Rich table.
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

    # Write the formatted output to the terminal.
    console.print(table)
