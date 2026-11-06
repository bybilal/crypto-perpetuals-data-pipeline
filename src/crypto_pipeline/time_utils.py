# Import datetime, timezone, timedelta from datetime for use below.
from datetime import datetime, timezone, timedelta
# Import integer_value from .normalization for use below.
from .normalization import integer_value

# Read the UTC retrieval time from a filename.
def filename_timestamp_ms(value):
    """Read the UTC retrieval time from a filename."""

    # Choose the value according to len(value) == 22; store the result in pattern.
    pattern = (
        "%Y%m%dT%H%M%S%fZ"
        if len(value) == 22
        else "%Y%m%dT%H%M%SZ"
    )

    # Parse a timestamp using the expected filename pattern; store the result in dt.
    dt = datetime.strptime(value, pattern)
    # Apply the specified replacement while keeping the remaining value intact; store the result in dt.
    dt = dt.replace(tzinfo=timezone.utc)

    # Calculate the difference between the supplied values; store the result in delta.
    delta = dt - datetime(1970, 1, 1, tzinfo=timezone.utc)
    # Return (delta.days * 86400 + delta.seconds) * 1000 + delta.microseconds // 1000 to the caller.
    return (delta.days * 86400 + delta.seconds) * 1000 + delta.microseconds // 1000


# Convert milliseconds to a readable UTC timestamp.
def utc_label(milliseconds):
    """Convert milliseconds to a readable UTC timestamp."""

    # Calculate datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=milliseconds); store the result in dt.
    dt = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=milliseconds)

    # Return dt.strftime('%Y-%m-%d %H:%M:%S UTC') to the caller.
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


# Distinguish older 1m files from 5m candle files.
def detect_interval(dataset, records):
    """Distinguish older 1m files from 5m candle files."""

    # Enter this branch only when dataset == 'oi'.
    if dataset == "oi":
        # Return '5m' to the caller.
        return "5m"

    # Enter this branch only when not records.
    if not records:
        # Return 'unknown' to the caller.
        return "unknown"

    # Run this operation with the error handling and cleanup defined below.
    try:
        # Build a collection by selecting and transforming the specified inputs; store the result in durations.
        durations = {
            integer_value(row[6], "close timestamp") - integer_value(row[0], "open timestamp") + 1
            for row in records
        }

    except (TypeError, IndexError, KeyError, ValueError):
        # Return 'unknown' to the caller.
        return "unknown"

    # Enter this branch only when durations == {300000}.
    if durations == {300_000}:
        # Return '5m' to the caller.
        return "5m"

    # Enter this branch only when durations == {60000}.
    if durations == {60_000}:
        # Return '1m' to the caller.
        return "1m"

    # Return 'unknown' to the caller.
    return "unknown"


