from datetime import datetime, timezone, timedelta
from .normalization import integer_value

def filename_timestamp_ms(value):
    """Read the UTC retrieval time from a filename."""

    pattern = (
        "%Y%m%dT%H%M%S%fZ"
        if len(value) == 22
        else "%Y%m%dT%H%M%SZ"
    )

    dt = datetime.strptime(value, pattern)
    dt = dt.replace(tzinfo=timezone.utc)

    delta = dt - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (delta.days * 86400 + delta.seconds) * 1000 + delta.microseconds // 1000


def utc_label(milliseconds):
    """Convert milliseconds to a readable UTC timestamp."""

    dt = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=milliseconds)

    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def detect_interval(dataset, records):
    """Distinguish older 1m files from 5m candle files."""

    if dataset == "oi":
        return "5m"

    if not records:
        return "unknown"

    try:
        durations = {
            integer_value(row[6], "close timestamp") - integer_value(row[0], "open timestamp") + 1
            for row in records
        }

    except (TypeError, IndexError, KeyError, ValueError):
        return "unknown"

    if durations == {300_000}:
        return "5m"

    if durations == {60_000}:
        return "1m"

    return "unknown"


