"""Strict hourly staging for TheFab21-derived energy/history statistics."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math

from .intuis_api.api import APIError

HOUR = 3600


def closed_hour_end(now: datetime) -> int:
    """Exclusive end: an hour must be closed for at least fifteen minutes."""
    if now.tzinfo is None:
        raise APIError("Hourly cutoff requires an aware clock")
    return (int(now.timestamp()) - 900) // HOUR * HOUR


def stage_hourly(samples, start: int, end: int):
    """Confirmed UTC hours of the period; deduplicate repeats, never add copies.

    Hours the cloud did not measure are absent, not zero: they stay a gap
    that a later run fills, and existing statistics for them are preserved.
    """
    if (type(start) is not int or type(end) is not int or start % HOUR or end % HOUR
            or end <= start or end-start > 731*86400):
        raise APIError("Invalid hourly period")
    values = {}
    for ts, wh in samples:
        if (type(ts) is not int or ts % HOUR or not start <= ts < end
                or isinstance(wh, bool) or not isinstance(wh, (int, float))
                or not math.isfinite(wh) or wh < 0):
            raise APIError("Invalid hourly measurement")
        if ts in values and values[ts] != wh:
            raise APIError("Conflicting hourly measurements")
        values[ts] = wh
    if not values:
        raise APIError("No measured hour in the period")
    return tuple((datetime.fromtimestamp(ts,timezone.utc),values[ts]/1000.0)
                 for ts in sorted(values))


def hourly_windows(samples):
    """Split chronological hourly samples into windows of consecutive hours."""
    windows = []
    for timestamp, value in samples:
        if windows and windows[-1][1] == timestamp:
            windows[-1][1] = timestamp + timedelta(hours=1)
            windows[-1][2].append((timestamp, value))
        else:
            windows.append([timestamp, timestamp + timedelta(hours=1), [(timestamp, value)]])
    return tuple((start, end, tuple(rows)) for start, end, rows in windows)


def sum_hourly(series_by_key):
    """Hour-by-hour sum over the hours confirmed by every series.

    An hour missing from any series is left out: a partial sum is never written.
    """
    series = [dict(values) for values in series_by_key.values()]
    if not series:
        return ()
    common = set.intersection(*(set(values) for values in series))
    return tuple(
        (hour, sum(values[hour] for values in series)) for hour in sorted(common)
    )


def home_total_status(total, hours: int) -> str:
    """'complete' when every requested hour was summed, else 'partial'.

    Hours some room has not confirmed yet keep their last home value and are
    filled by a later run.
    """
    return "complete" if len(total) == hours else "partial"
