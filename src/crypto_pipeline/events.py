"""File-only operational events, independent of Rich's terminal console."""
# Import contextmanager from contextlib for use below.
from contextlib import contextmanager
# Import ContextVar from contextvars for use below.
from contextvars import ContextVar
# Import datetime, timezone from datetime for use below.
from datetime import datetime, timezone
# Import json for use below.
import json
# Import re for use below.
import re
# Import uuid for use below.
import uuid

# Keep each execution context associated with its own run ID and log files.
_current = ContextVar("pipeline_log", default=None)
# Recognize ANSI terminal escape sequences so they can be excluded from human logs.
_ansi = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")

# Define emit with the inputs listed below.
def emit(stage, event, **fields):
    # Find the logging context for this run; direct helper calls may have no active logger.
    sink = _current.get()
    # Do nothing when no pipeline run has configured file logging.
    if sink is None:
        # Stop this function without returning a result.
        return
    # Use sink; store the result in (machine, human, run_id).
    machine, human, run_id = sink
    # Build the named fields used by this operation; store the result in row.
    row = {"timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
           "run_id": run_id, "stage": stage, "event": event, **fields}
    # Append one JSON object and newline: each line is an independently readable event.
    machine.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    # Flush buffered text so this event is available to readers immediately.
    machine.flush()
    # Also write/show the optional human-readable log when enabled.
    if human:
        # JSON-escaped field values also prevent control characters or multiline injection.
        details = json.dumps(fields, ensure_ascii=True, default=str)
        # Write the same event as timestamp, run ID, stage and details, without terminal colors.
        human.write(_ansi.sub("", f"{row['timestamp']} {run_id} {stage}: {event} {details}") + "\n")
        # Flush buffered text so this event is available to readers immediately.
        human.flush()

# Define logging run with the inputs listed below.
@contextmanager
def logging_run(directory, human=False):
    # Create the needed output directory, including missing parents.
    directory.mkdir(parents=True, exist_ok=True)
    # Generate a unique run ID that links terminal output to both log filenames.
    run_id = uuid.uuid4().hex
    # Manage (directory / f'{run_id}.jsonl').open('x', encoding='utf-8') with automatic context cleanup on exit.
    with (directory / f"{run_id}.jsonl").open("x", encoding="utf-8") as machine:
        # Choose the value according to human; store the result in human_file.
        human_file = (directory / f"{run_id}.log").open("x", encoding="utf-8") if human else None
        # Set the context-local logging sink for the current run; store the result in token.
        token = _current.set((machine, human_file, run_id))
        # Run this operation with the error handling and cleanup defined below.
        try:
            # Let the pipeline run with these log files open; resume here when its context exits.
            yield run_id
        finally:
            # Restore the previous context-local logging sink during cleanup.
            _current.reset(token)
            # Close the optional human log only if it was opened.
            if human_file:
                # Close the open resource and release its operating-system handle.
                human_file.close()
