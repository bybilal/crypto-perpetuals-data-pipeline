"""A process lock for the single-machine SQLite pipeline (macOS/Linux)."""
# Context managers release the lock even if fetching or loading raises an exception.
from contextlib import contextmanager
# flock is released by the operating system when its process exits or crashes.
import fcntl


@contextmanager
def pipeline_lock(db_path):
    """Serialize CLI runs targeting the same resolved database path."""
    # Resolve aliases so symlinked paths share one lock file.
    path = db_path.resolve().with_suffix(db_path.suffix + ".lock")
    # The first run can create the database directory before SQLite is opened.
    path.parent.mkdir(parents=True, exist_ok=True)
    # Keep this file in place: unlinking an active lock file could allow a second writer.
    with path.open("a") as lock:
        try:
            # Fail promptly instead of queuing another fetch behind an active run.
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("Another pipeline run is already using this database") from error
        try:
            # Hold the lock through both fetching and database ingestion.
            yield
        finally:
            # Always release the lock, including after failed or interrupted runs.
            fcntl.flock(lock, fcntl.LOCK_UN)
