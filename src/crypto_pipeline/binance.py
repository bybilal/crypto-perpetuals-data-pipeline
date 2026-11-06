
# Import json for use below.
import json
# Import Path from pathlib for use below.
from pathlib import Path
# Import datetime, timezone from datetime for use below.
from datetime import datetime, timezone
# Import urlencode from urllib.parse for use below.
from urllib.parse import urlencode
# Import urlopen from urllib.request for use below.
from urllib.request import urlopen
# Import HTTPError, URLError from urllib.error for use below.
from urllib.error import HTTPError, URLError

# Import console, display_response, display_error, display_contract_metadata from .reporting for use below.
from .reporting import (
    console,
    display_response,
    display_error,
    display_contract_metadata,
)


# ----------------------------------------
# API CONFIGURATION
# ----------------------------------------

# Use the explicit text 'https://fapi.binance.com'; store the result in BASE_URL.
BASE_URL = "https://fapi.binance.com"

# Build the ordered collection used by this operation; store the result in SYMBOLS.
SYMBOLS = ["BTCUSDT", "1000PEPEUSDT"]

# Use the explicit text '5m'; store the result in INTERVAL.
INTERVAL = "5m"
# Set the explicit starting value; store the result in LIMIT.
LIMIT = 3

# Build the named fields used by this operation; store the result in ENDPOINTS.
ENDPOINTS = {
    "oi": (
        "/futures/data/openInterestHist",
        {"period": INTERVAL, "limit": LIMIT},
    ),
    "klines": (
        "/fapi/v1/klines",
        {"interval": INTERVAL, "limit": LIMIT},
    ),
}


# ----------------------------------------
# FILE PATHS
# ----------------------------------------

# Import PROJECT_ROOT, RAW_DIR from .config for use below.
from .config import PROJECT_ROOT, RAW_DIR

# ----------------------------------------
# SHARED REQUEST HELPER
# ----------------------------------------

# Fetch and preserve the original API response.
def request_and_save(url, filename_prefix):
    """Fetch and preserve the original API response."""

    # Manage urlopen(url, timeout=10) with automatic context cleanup on exit.
    with urlopen(url, timeout=10) as response:
        # Read the original HTTP response bytes before any JSON decoding changes their representation.
        raw_bytes = response.read()

    # Format the timestamp using the explicit date/time pattern; store the result in timestamp.
    timestamp = datetime.now(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%S%fZ")

    # Construct the path or ratio from the specified components; store the result in path.
    path = RAW_DIR / f"{filename_prefix}_{timestamp}.json"

    # Store original bytes before parsing.
    path.write_bytes(raw_bytes)

    # Return (json.loads(raw_bytes), path) to the caller.
    return json.loads(raw_bytes), path


# ----------------------------------------
# CONTRACT METADATA
# ----------------------------------------

# Fetch Binance exchange metadata once per run.
def fetch_exchange_info():
    """Fetch Binance exchange metadata once per run."""

    # Build the text using the current field values; store the result in url.
    url = f"{BASE_URL}/fapi/v1/exchangeInfo"

    # Save original response bytes before parsing the returned JSON; store the result in (payload, path).
    payload, path = request_and_save(
        url,
        "exchangeInfo",
    )

    # Enter this branch only when not isinstance(payload, dict).
    if not isinstance(payload, dict):
        # Stop this operation with ValueError('Expected exchangeInfo JSON object').
        raise ValueError("Expected exchangeInfo JSON object")

    # Read the requested optional value using its default when absent; store the result in all_contracts.
    all_contracts = payload.get("symbols")

    # Enter this branch only when not isinstance(all_contracts, list).
    if not isinstance(all_contracts, list):
        # Stop this operation with ValueError('Missing exchangeInfo symbols list').
        raise ValueError("Missing exchangeInfo symbols list")

    # Build a collection by selecting and transforming the specified inputs; store the result in by_symbol.
    by_symbol = {
        item["symbol"]: item
        for item in all_contracts
        if isinstance(item, dict) and "symbol" in item
    }

    # Build a collection by selecting and transforming the specified inputs; store the result in missing.
    missing = [
        symbol
        for symbol in SYMBOLS
        if symbol not in by_symbol
    ]

    # Enter this branch only when missing.
    if missing:
        # Stop this operation with ValueError(f'Contracts not found in exchangeInfo: {missing}').
        raise ValueError(
            f"Contracts not found in exchangeInfo: {missing}"
        )

    # Build a collection by selecting and transforming the specified inputs; store the result in selected.
    selected = [by_symbol[symbol] for symbol in SYMBOLS]

    # Show the exchange-supplied contract identifiers and trading increments.
    display_contract_metadata(
        contracts=selected,
        path=path,
        project_root=PROJECT_ROOT,
    )


# ----------------------------------------
# MARKET DATA INGESTION
# ----------------------------------------

# Fetch market observations and contract metadata.
def fetch_market_data():
    """Fetch market observations and contract metadata."""

    # Create the needed output directory, including missing parents.
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    # Build the named fields used by this operation; store the result in stats.
    stats = {
        "successful_requests": 0,
        "failed_requests": 0,
        "saved_files": 0,
    }

    # Fetch OI and 5m candles for each symbol.
    for symbol in SYMBOLS:
        # Process each (name, (endpoint, parameters)) from ENDPOINTS.items().
        for name, (endpoint, parameters) in ENDPOINTS.items():

            # Encode the symbol and endpoint parameters into a URL query string; store the result in query.
            query = urlencode({
                "symbol": symbol,
                **parameters,
            })

            # Build the text using the current field values; store the result in url.
            url = f"{BASE_URL}{endpoint}?{query}"

            # Run this operation with the error handling and cleanup defined below.
            try:
                # Save original response bytes before parsing the returned JSON; store the result in (data, path).
                data, path = request_and_save(
                    url,
                    f"{symbol}_{name}",
                )

                # Update stats['saved_files'] using 1 for this step.
                stats["saved_files"] += 1

                # Enter this branch only when not isinstance(data, list).
                if not isinstance(data, list):
                    # Stop this operation with ValueError('Expected an API response list').
                    raise ValueError(
                        "Expected an API response list"
                    )

                # Show a readable sample of the returned market data and its saved path.
                display_response(
                    symbol=symbol,
                    dataset=name,
                    interval=INTERVAL,
                    data=data,
                    path=path,
                    project_root=PROJECT_ROOT,
                )

                # Update stats['successful_requests'] using 1 for this step.
                stats["successful_requests"] += 1

            except HTTPError as error:
                # Update stats['failed_requests'] using 1 for this step.
                stats["failed_requests"] += 1

                # Read error.read().decode('utf-8', errors='replace')[:250] from the source data; store the result in details.
                details = error.read().decode(
                    "utf-8",
                    errors="replace",
                )[:250]

                # Record the request failure and show its details in the terminal.
                display_error(
                    symbol,
                    name,
                    "HTTP error",
                    f"{error.code} — {details}",
                )

            except (
                URLError,
                TimeoutError,
                ValueError,
                KeyError,
                IndexError,
                TypeError,
                OSError,
            ) as error:
                # Update stats['failed_requests'] using 1 for this step.
                stats["failed_requests"] += 1

                # Record the request failure and show its details in the terminal.
                display_error(
                    symbol,
                    name,
                    "Request or data error",
                    str(error),
                )

    # Fetch exchange-wide metadata once, not per symbol.
    try:
        # Fetch one exchangeInfo response and inspect the selected contracts.
        fetch_exchange_info()

        # Update stats['successful_requests'] using 1 for this step.
        stats["successful_requests"] += 1
        # Update stats['saved_files'] using 1 for this step.
        stats["saved_files"] += 1

    except HTTPError as error:
        # Update stats['failed_requests'] using 1 for this step.
        stats["failed_requests"] += 1

        # Read error.read().decode('utf-8', errors='replace')[:250] from the source data; store the result in details.
        details = error.read().decode(
            "utf-8",
            errors="replace",
        )[:250]

        # Record the request failure and show its details in the terminal.
        display_error(
            "BINANCE",
            "exchangeInfo",
            "HTTP error",
            f"{error.code} — {details}",
        )

    except (
        URLError,
        TimeoutError,
        ValueError,
        KeyError,
        TypeError,
        OSError,
    ) as error:
        # Update stats['failed_requests'] using 1 for this step.
        stats["failed_requests"] += 1

        # Record the request failure and show its details in the terminal.
        display_error(
            "BINANCE",
            "exchangeInfo",
            "Request or data error",
            str(error),
        )

    # Return stats to the caller.
    return stats


# ----------------------------------------
# DIRECT EXECUTION
# ----------------------------------------

# Define main with the inputs listed below.
def main():
    # Fetch and save the configured Binance market-data responses; store the result in stats.
    stats = fetch_market_data()

    # Write the formatted output to the terminal.
    console.print()
    # Write the formatted output to the terminal.
    console.print(
        f"[grey62]Requests successful:[/grey62] "
        f"{stats['successful_requests']}"
    )
    # Write the formatted output to the terminal.
    console.print(
        f"[grey62]Requests failed:[/grey62] "
        f"{stats['failed_requests']}"
    )

    # Return 1 if stats['failed_requests'] else 0 to the caller.
    return 1 if stats["failed_requests"] else 0


# Run this entry point only when the file is executed directly.
if __name__ == "__main__":
    # Stop this operation with SystemExit(main()).
    raise SystemExit(main())
