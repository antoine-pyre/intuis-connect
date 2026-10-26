"""Strict hourly staging for TheFab21-derived energy/history statistics."""
from __future__ import annotations

from datetime import datetime, timezone
import math

from .intuis_api.api import APIError

HOUR = 3600


def closed_hour_end(now: datetime) -> int:
    """Exclusive end: an hour must be closed for at least fifteen minutes."""
    if now.tzinfo is None:
        raise APIError("Hourly cutoff requires an aware clock")
    return (int(now.timestamp()) - 900) // HOUR * HOUR


def stage_hourly(samples, start: int, end: int):
    """Exact UTC-hour coverage; deduplicate repeated values, never add copies."""
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
    if set(values) != set(range(start,end,HOUR)):
        raise APIError("Incomplete hourly coverage")
    return tuple((datetime.fromtimestamp(ts,timezone.utc),values[ts]/1000.0)
                 for ts in sorted(values))
