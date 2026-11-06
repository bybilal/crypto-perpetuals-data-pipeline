
import argparse
from time import perf_counter

from .reporting import console
from .binance import fetch_market_data
from .storage.loader import RAW_DIR, DB_PATH, main as load_sqlite


# ----------------------------------------
# TERMINAL OUTPUT
# ----------------------------------------

def display_stage(number, title):
    console.print()
    console.print(
        f"[#8EAABD]Stage {number} / {title}[/#8EAABD]"
    )
    console.print()


# ----------------------------------------
# PIPELINE CONTROLLER
# ----------------------------------------

def run_pipeline(offline=False):
    """
    Coordinate the local ingestion pipeline.

    Offline mode processes existing JSON files
    without making network requests.
    """

    started = perf_counter()

    console.print()
    console.print(
        "[#8EAABD]Market Data Pipeline / 5m[/#8EAABD]"
    )

    # Stage 1: Fetch source data.
    display_stage(1, "Fetch")

    if offline:
        console.print(
            "  [grey62]Offline mode — API requests skipped[/grey62]"
        )

    else:
        stats = fetch_market_data()

        console.print()
        console.print(
            f"  [grey62]Successful requests[/grey62]  "
            f"{stats['successful_requests']}"
        )
        console.print(
            f"  [grey62]Failed requests[/grey62]      "
            f"{stats['failed_requests']}"
        )
        console.print(
            f"  [grey62]Raw files saved[/grey62]      "
            f"{stats['saved_files']}"
        )

        if stats["failed_requests"]:
            raise RuntimeError(
                "Fetch stage incomplete. "
                "Successfully saved raw files remain available. "
                "Resolve the errors or rerun with --offline."
            )

    # Check that local source files are available.
    if not RAW_DIR.exists() or not any(RAW_DIR.glob("*.json")):
        raise FileNotFoundError(
            "No raw JSON files found in data/raw/"
        )

    # Stage 2: Normalize and load.
    display_stage(2, "Normalize + SQLite")

    load_sqlite()

    if not DB_PATH.exists():
        raise RuntimeError(
            "SQLite database was not created"
        )

    # Completion.
    elapsed = perf_counter() - started

    console.print()
    console.print(
        "[#8EAABD]Pipeline completed[/#8EAABD]"
    )
    console.print(
        f"  [grey62]Mode[/grey62]      "
        f"{'Offline' if offline else 'Online'}"
    )
    console.print(
        f"  [grey62]Duration[/grey62]  {elapsed:.2f}s"
    )
    console.print()


# ----------------------------------------
# COMMAND-LINE INTERFACE
# ----------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Run the local crypto market data pipeline"
    )

    parser.add_argument(
        "--offline",
        action="store_true",
        help="Load saved JSON without fetching Binance data",
    )

    args = parser.parse_args()

    try:
        run_pipeline(offline=args.offline)
        return 0

    except Exception as error:
        console.print()
        console.print(
            f"[red]Pipeline failed:[/red] {error}"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
