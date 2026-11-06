
# Import argparse for use below.
import argparse
from .locking import pipeline_lock
from .coverage import display_recent_coverage
# Import perf_counter from time for use below.
from time import perf_counter
# Import Path from pathlib for use below.
from pathlib import Path
# Import emit, logging_run from .events for use below.
from .events import emit, logging_run
# Import PROJECT_ROOT from .config for use below.
from .config import PROJECT_ROOT
# Import loader from .storage for use below.
from .storage import loader
# Import binance from . for use below.
from . import binance

# Import console from .reporting for use below.
from .reporting import console
# Import fetch_market_data from .binance for use below.
from .binance import fetch_market_data
# Import RAW_DIR, DB_PATH, main from .storage.loader for use below.
from .storage.loader import RAW_DIR, DB_PATH, main as load_sqlite


# ----------------------------------------
# TERMINAL OUTPUT
# ----------------------------------------

# Define display stage with the inputs listed below.
def display_stage(number, title):
    # Write the formatted output to the terminal.
    console.print()
    # Use a warm brown to distinguish stage headings from blue contract labels.
    console.print(
        f"[#B08D72]Stage {number} / {title}[/#B08D72]"
    )
    # Write the formatted output to the terminal.
    console.print()


# ----------------------------------------
# PIPELINE CONTROLLER
# ----------------------------------------

# Coordinate the local ingestion pipeline.
def run_pipeline(offline=False, limit=3, coverage=False):
    """
    Coordinate the local ingestion pipeline.

    Offline mode processes existing JSON files
    without making network requests.
    """

    # Read a monotonic timer for measuring elapsed execution time; store the result in started.
    started = perf_counter()
    # Write this stage event to the active run logs without printing to the terminal.
    emit("pipeline", "started", offline=offline)

    # Write the formatted output to the terminal.
    console.print()
    # Write the formatted output to the terminal.
    console.print(
        "[#8EAABD]Market Data Pipeline / 5m[/#8EAABD]"
    )

    # Stage 1: Fetch source data.
    display_stage(1, "Fetch")

    # Write this stage event to the active run logs without printing to the terminal.
    emit("fetch", "started", offline=offline)
    # Skip network requests when processing previously saved files.
    if offline:
        # Write the formatted output to the terminal.
        console.print(
            "  [grey62]Offline mode — API requests skipped[/grey62]"
        )

    else:
        # Fetch and save the configured Binance market-data responses; store the result in stats.
        stats = fetch_market_data(limit=limit)

        # Write the formatted output to the terminal.
        console.print()
        # Write the formatted output to the terminal.
        console.print(
            f"  [grey62]Successful requests[/grey62]  "
            f"{stats['successful_requests']}"
        )
        # Write the formatted output to the terminal.
        console.print(
            f"  [grey62]Failed requests[/grey62]      "
            f"{stats['failed_requests']}"
        )
        # Write the formatted output to the terminal.
        console.print(
            f"  [grey62]Raw files saved[/grey62]      "
            f"{stats['saved_files']}"
        )

        # Enter this branch only when stats['failed_requests'].
        if stats["failed_requests"]:
            # Stop before loading if any request failed; previously saved raw responses remain available.
            raise RuntimeError(
                "Fetch stage incomplete. "
                "Successfully saved raw files remain available. "
                "Resolve the errors or rerun with --offline."
            )

    # Write this stage event to the active run logs without printing to the terminal.
    emit("fetch", "skipped" if offline else "completed", **({} if offline else {"counts": stats}))

    # Check that local source files are available.
    if not RAW_DIR.exists() or not any(RAW_DIR.glob("*.json")):
        # Stop this operation with FileNotFoundError('No raw JSON files found in data/raw/').
        raise FileNotFoundError(
            "No raw JSON files found in data/raw/"
        )

    # Stage 2: Normalize and load.
    display_stage(2, "Normalize + SQLite")

    # Write this stage event to the active run logs without printing to the terminal.
    emit("load", "started")
    # Run the schema, metadata and observation loading stages; store the result in load_stats.
    load_stats = load_sqlite()

    # Enter this branch only when not DB_PATH.exists().
    if not DB_PATH.exists():
        # Stop this operation with RuntimeError('SQLite database was not created').
        raise RuntimeError(
            "SQLite database was not created"
        )

    # Write this stage event to the active run logs without printing to the terminal.
    emit("pipeline", "completed", quality_warnings=bool(load_stats and (load_stats["invalid_records"] or load_stats["file_errors"])))

    # Enter this branch only when load_stats and (load_stats['invalid_records'] or load_stats['file_errors']).
    if load_stats and (load_stats["invalid_records"] or load_stats["file_errors"]):
        # Write the formatted output to the terminal.
        console.print("[yellow]Completed with data-quality warnings; see the run log for details.[/yellow]")

    # Optional monitoring checks each stream independently over the last hour.
    if coverage:
        display_recent_coverage(DB_PATH)

    # Completion.
    elapsed = perf_counter() - started

    # Write the formatted output to the terminal.
    console.print()
    # Write the formatted output to the terminal.
    console.print(
        "[#8EAABD]Pipeline completed[/#8EAABD]"
    )
    # Write the formatted output to the terminal.
    console.print(
        f"  [grey62]Mode[/grey62]      "
        f"{'Offline' if offline else 'Online'}"
    )
    # Write the formatted output to the terminal.
    console.print(
        f"  [grey62]Duration[/grey62]  {elapsed:.2f}s"
    )
    # Write the formatted output to the terminal.
    console.print()


# ----------------------------------------
# COMMAND-LINE INTERFACE
# ----------------------------------------

# Define main with the inputs listed below.
def main():
    # Define the command-line interface and its help text; store the result in parser.
    parser = argparse.ArgumentParser(
        description="Run the local crypto market data pipeline"
    )

    # Declare this command-line option, including its default or help text.
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Load saved JSON without fetching Binance data",
    )

    # Declare this command-line option, including its default or help text.
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    # Declare this command-line option, including its default or help text.
    parser.add_argument("--db-path", type=Path, default=DB_PATH)
    # Declare this command-line option, including its default or help text.
    parser.add_argument("--log-dir", type=Path, default=PROJECT_ROOT / "logs")
    # Declare this command-line option, including its default or help text.
    parser.add_argument("--human-log", action="store_true", help="Also write a plain-text operational log")
    # Parse the supplied command-line options and their defaults; store the result in args.
    # Overlapping recent batches recover observations missed during brief interruptions.
    parser.add_argument("--limit", type=int, default=3, choices=range(1, 501), metavar="1..500")
    # Show and log separate candle and OI coverage over mature boundaries.
    parser.add_argument("--coverage", action="store_true", help="Report last-hour OI/candle coverage")
    args = parser.parse_args()
    # Apply command-line paths consistently to fetching and database loading.
    global_paths(args)


    # Run this operation with the error handling and cleanup defined below.
    try:
        # Open this run's log files and restore the logging context when the run ends.
        with logging_run(args.log_dir, human=args.human_log) as run_id:
            # Run this operation with the error handling and cleanup defined below.
            try:
                # Coordinate fetch, normalization, database storage and terminal reporting.
                # Serialize manual and scheduled CLI runs through the same database lock.
                with pipeline_lock(DB_PATH):
                    run_pipeline(offline=args.offline, limit=args.limit, coverage=args.coverage)
            except Exception as error:
                # Write this stage event to the active run logs without printing to the terminal.
                emit("pipeline", "failed", error_type=type(error).__name__, error=str(error))
                # Propagate the current error to the caller.
                raise
            finally:
                # Print the current run ID and the locations of its log files.
                display_run_logs(args.log_dir, run_id, args.human_log)
        # Return 0 to the caller.
        return 0
    except Exception as error:
        # Write the formatted output to the terminal.
        console.print()
        # Write the formatted output to the terminal.
        console.print(f"[red]Pipeline failed:[/red] {error}")
        # Return 1 to the caller.
        return 1


# Show where to find this run after its terminal output has disappeared.
def display_run_logs(directory, run_id, human):
    """Show where to find this run after its terminal output has disappeared."""
    # Write the formatted output to the terminal.
    console.print(f"[grey62]Run:[/grey62] {run_id}")
    # Write the formatted output to the terminal.
    console.print("JSONL log: " + log_path_label(directory / f"{run_id}.jsonl"), style="grey62", markup=False)
    # Also write/show the optional human-readable log when enabled.
    if human:
        # Write the formatted output to the terminal.
        console.print("Human log: " + log_path_label(directory / f"{run_id}.log"), style="grey62", markup=False)
    # Write the formatted output to the terminal.
    console.print()


# Keep local paths compact; preserve full paths for external log folders.
def log_path_label(path):
    """Keep local paths compact; preserve full paths for external log folders."""
    # Resolve this path to its full filesystem location; store the result in resolved.
    resolved = path.resolve()
    # Use a repository-relative path for local logs, otherwise display the full external path.
    return str(resolved.relative_to(PROJECT_ROOT) if resolved.is_relative_to(PROJECT_ROOT) else resolved)


# Configure legacy-compatible entry points consistently.
def global_paths(args):
    """Configure legacy-compatible entry points consistently."""
    # Update these shared module settings rather than creating local variables.
    global RAW_DIR, DB_PATH
    # Resolve this path to its full filesystem location; store the result in RAW_DIR, loader.RAW_DIR, binance.RAW_DIR.
    RAW_DIR = loader.RAW_DIR = binance.RAW_DIR = args.raw_dir.resolve()
    # Resolve this path to its full filesystem location; store the result in DB_PATH, loader.DB_PATH.
    DB_PATH = loader.DB_PATH = args.db_path.resolve()


# Run this entry point only when the file is executed directly.
if __name__ == "__main__":
    # Stop this operation with SystemExit(main()).
    raise SystemExit(main())
