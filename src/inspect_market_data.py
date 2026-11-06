
import json
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import urlopen
from urllib.error import HTTPError, URLError

from format_market_data import (
    console,
    display_response,
    display_error,
    display_contract_metadata,
)


# ----------------------------------------
# API CONFIGURATION
# ----------------------------------------

BASE_URL = "https://fapi.binance.com"

SYMBOLS = ["BTCUSDT", "1000PEPEUSDT"]

INTERVAL = "5m"
LIMIT = 3

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

SCRIPT_DIR = Path(__file__).resolve().parent

PROJECT_ROOT = (
    SCRIPT_DIR.parent
    if SCRIPT_DIR.name == "src"
    else SCRIPT_DIR
)

RAW_DIR = PROJECT_ROOT / "data" / "raw"


# ----------------------------------------
# SHARED REQUEST HELPER
# ----------------------------------------

def request_and_save(url, filename_prefix):
    """Fetch and preserve the original API response."""

    with urlopen(url, timeout=10) as response:
        raw_bytes = response.read()

    timestamp = datetime.now(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%S%fZ")

    path = RAW_DIR / f"{filename_prefix}_{timestamp}.json"

    # Store original bytes before parsing.
    path.write_bytes(raw_bytes)

    return json.loads(raw_bytes), path


# ----------------------------------------
# CONTRACT METADATA
# ----------------------------------------

def fetch_exchange_info():
    """Fetch Binance exchange metadata once per run."""

    url = f"{BASE_URL}/fapi/v1/exchangeInfo"

    payload, path = request_and_save(
        url,
        "exchangeInfo",
    )

    if not isinstance(payload, dict):
        raise ValueError("Expected exchangeInfo JSON object")

    all_contracts = payload.get("symbols")

    if not isinstance(all_contracts, list):
        raise ValueError("Missing exchangeInfo symbols list")

    by_symbol = {
        item["symbol"]: item
        for item in all_contracts
        if isinstance(item, dict) and "symbol" in item
    }

    missing = [
        symbol
        for symbol in SYMBOLS
        if symbol not in by_symbol
    ]

    if missing:
        raise ValueError(
            f"Contracts not found in exchangeInfo: {missing}"
        )

    selected = [by_symbol[symbol] for symbol in SYMBOLS]

    display_contract_metadata(
        contracts=selected,
        path=path,
        project_root=PROJECT_ROOT,
    )


# ----------------------------------------
# MARKET DATA INGESTION
# ----------------------------------------

def fetch_market_data():
    """Fetch market observations and contract metadata."""

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    stats = {
        "successful_requests": 0,
        "failed_requests": 0,
        "saved_files": 0,
    }

    # Fetch OI and 5m candles for each symbol.
    for symbol in SYMBOLS:
        for name, (endpoint, parameters) in ENDPOINTS.items():

            query = urlencode({
                "symbol": symbol,
                **parameters,
            })

            url = f"{BASE_URL}{endpoint}?{query}"

            try:
                data, path = request_and_save(
                    url,
                    f"{symbol}_{name}",
                )

                stats["saved_files"] += 1

                if not isinstance(data, list):
                    raise ValueError(
                        "Expected an API response list"
                    )

                display_response(
                    symbol=symbol,
                    dataset=name,
                    interval=INTERVAL,
                    data=data,
                    path=path,
                    project_root=PROJECT_ROOT,
                )

                stats["successful_requests"] += 1

            except HTTPError as error:
                stats["failed_requests"] += 1

                details = error.read().decode(
                    "utf-8",
                    errors="replace",
                )[:250]

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
                stats["failed_requests"] += 1

                display_error(
                    symbol,
                    name,
                    "Request or data error",
                    str(error),
                )

    # Fetch exchange-wide metadata once, not per symbol.
    try:
        fetch_exchange_info()

        stats["successful_requests"] += 1
        stats["saved_files"] += 1

    except HTTPError as error:
        stats["failed_requests"] += 1

        details = error.read().decode(
            "utf-8",
            errors="replace",
        )[:250]

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
        stats["failed_requests"] += 1

        display_error(
            "BINANCE",
            "exchangeInfo",
            "Request or data error",
            str(error),
        )

    return stats


# ----------------------------------------
# DIRECT EXECUTION
# ----------------------------------------

def main():
    stats = fetch_market_data()

    console.print()
    console.print(
        f"[grey62]Requests successful:[/grey62] "
        f"{stats['successful_requests']}"
    )
    console.print(
        f"[grey62]Requests failed:[/grey62] "
        f"{stats['failed_requests']}"
    )

    return 1 if stats["failed_requests"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
