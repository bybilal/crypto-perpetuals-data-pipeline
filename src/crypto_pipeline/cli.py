
import argparse
from time import perf_counter
from pathlib import Path
from .events import emit, logging_run
from .config import PROJECT_ROOT
from .storage import loader
from . import binance

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
    emit("pipeline", "started", offline=offline)

    console.print()
    console.print(
        "[#8EAABD]Market Data Pipeline / 5m[/#8EAABD]"
    )

    # Stage 1: Fetch source data.
    display_stage(1, "Fetch")

    emit("fetch", "started", offline=offline)
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

    emit("fetch", "skipped" if offline else "completed", **({} if offline else {"counts": stats}))

    # Check that local source files are available.
    if not RAW_DIR.exists() or not any(RAW_DIR.glob("*.json")):
        raise FileNotFoundError(
            "No raw JSON files found in data/raw/"
        )

    # Stage 2: Normalize and load.
    display_stage(2, "Normalize + SQLite")

    emit("load", "started")
    load_stats = load_sqlite()

    if not DB_PATH.exists():
        raise RuntimeError(
            "SQLite database was not created"
        )

    emit("pipeline", "completed", quality_warnings=bool(load_stats and (load_stats["invalid_records"] or load_stats["file_errors"])))

    if load_stats and (load_stats["invalid_records"] or load_stats["file_errors"]):
        console.print("[yellow]Completed with data-quality warnings; see the run log for details.[/yellow]")

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

    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--db-path", type=Path, default=DB_PATH)
    parser.add_argument("--log-dir", type=Path, default=PROJECT_ROOT / "logs")
    parser.add_argument("--human-log", action="store_true", help="Also write a plain-text operational log")
    args = parser.parse_args()
    global_paths(args)


    try:
        with logging_run(args.log_dir, human=args.human_log) as run_id:
            try:
                run_pipeline(offline=args.offline)
            except Exception as error:
                emit("pipeline", "failed", error_type=type(error).__name__, error=str(error))
                raise
            finally:
                display_run_logs(args.log_dir, run_id, args.human_log)
        return 0
    except Exception as error:
        console.print()
        console.print(f"[red]Pipeline failed:[/red] {error}")
        return 1


def display_run_logs(directory, run_id, human):
    """Show where to find this run after its terminal output has disappeared."""
    console.print(f"[grey62]Run:[/grey62] {run_id}")
    console.print("JSONL log: " + log_path_label(directory / f"{run_id}.jsonl"), style="grey62", markup=False)
    if human:
        console.print("Human log: " + log_path_label(directory / f"{run_id}.log"), style="grey62", markup=False)
    console.print()


def log_path_label(path):
    """Keep local paths compact; preserve full paths for external log folders."""
    resolved = path.resolve()
    return str(resolved.relative_to(PROJECT_ROOT) if resolved.is_relative_to(PROJECT_ROOT) else resolved)


def global_paths(args):
    """Configure legacy-compatible entry points consistently."""
    global RAW_DIR, DB_PATH
    RAW_DIR = loader.RAW_DIR = binance.RAW_DIR = args.raw_dir.resolve()
    DB_PATH = loader.DB_PATH = args.db_path.resolve()


if __name__ == "__main__":
    raise SystemExit(main())
