"""Daily rebase of the cumulative energy level.

Adapted from TheFab21's Node-RED flow (TheFab21/Time-Planning-intuis), which
has run against this cloud for a long time.

The hourly series on its own is purely relative: ``_replace_windows`` continues
sums from the row preceding the written period, so a missed or revised hour
enters the cumulative sum and stays there for good, and an overlapping
re-import shifts everything after it.

The flow avoids that by keeping an absolute level settled at the end of a local
day the cloud has had time to consolidate, advancing it once a day from the
``1day`` measure, and deriving every later hour as "level + running total since
local midnight". This module provides that level; ``hourly_stats`` writes the
hours against it.

Two days of settling, rather than one, leave the cloud a full day to finish
revising a day before it is taken as final.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import math
from typing import Any, Mapping
from zoneinfo import ZoneInfo

SETTLE_DAYS = 2
# Beyond this lag the level is re-seeded instead of replayed: a longer hourly
# window would cost more than the correction is worth.
MAX_CATCH_UP_DAYS = 14


def local_midnight(day: date, zone: ZoneInfo) -> datetime:
    """Start of a local day, as an aware datetime."""
    return datetime(day.year, day.month, day.day, tzinfo=zone)


def settled_day(now: datetime, zone: ZoneInfo, settle_days: int = SETTLE_DAYS) -> date:
    """Last local day the cloud is assumed to have consolidated."""
    if now.tzinfo is None:
        raise ValueError("Settled day requires an aware clock")
    return now.astimezone(zone).date() - timedelta(days=settle_days)


def daily_totals(
    samples: list[tuple[int, float]], zone: ZoneInfo, first: date, last: date
) -> dict[date, float]:
    """Measured kWh per local day of [first, last], ignoring anything else.

    The cloud stamps a day inside it, at local noon, so a sample belongs to the
    local day containing its timestamp. A day without a measurement is absent,
    never a fabricated zero: it simply adds nothing to the level.
    """
    totals: dict[date, float] = {}
    for timestamp, wh in samples:
        if (
            isinstance(timestamp, bool)
            or not isinstance(timestamp, (int, float))
            or not math.isfinite(timestamp)
            or timestamp != int(timestamp)
            or isinstance(wh, bool)
            or not isinstance(wh, (int, float))
            or not math.isfinite(wh)
            or wh < 0
        ):
            raise ValueError("Invalid daily timestamp or energy value")
        day = datetime.fromtimestamp(int(timestamp), timezone.utc).astimezone(zone).date()
        if not first <= day <= last:
            continue
        if day in totals:
            raise ValueError(f"Duplicate daily measurement for {day.isoformat()}")
        totals[day] = wh / 1000.0
    return totals


@dataclass(frozen=True)
class RebasePlan:
    """One catch-up: the local days to add, and the UTC range to request."""

    first: date
    last: date
    begin: int
    end: int

    @property
    def days(self) -> int:
        return (self.last - self.first).days + 1


class EnergyBase:
    """Per-room cumulative levels settled at the end of a local day.

    Stored inside the import manager's state so one entry keeps one level set,
    saved with the rest of its progress.
    """

    def __init__(self, state: dict[str, Any]) -> None:
        self._root = state
        section = state.get("energy_base")
        if not isinstance(section, dict):
            section = {}
            state["energy_base"] = section
        self._state = section
        if not isinstance(self._state.get("levels"), dict):
            self._state["levels"] = {}

    @property
    def settled_through(self) -> date | None:
        """Local day whose end the levels describe, or None before seeding."""
        raw = self._state.get("settled_through")
        try:
            return date.fromisoformat(raw) if isinstance(raw, str) else None
        except ValueError:
            return None

    def level(self, room_id: str) -> float | None:
        """Cumulative kWh at the end of ``settled_through``, if known."""
        value = self._state["levels"].get(room_id)
        return float(value) if isinstance(value, (int, float)) else None

    def seed(self, through: date, levels: Mapping[str, float]) -> None:
        """Adopt an existing cumulative level without calling the cloud.

        Taking the series' own last sum keeps the first write continuous: the
        rebase stops drift from growing rather than repairing what is past.
        """
        self._state["settled_through"] = through.isoformat()
        self._state["levels"] = {
            room_id: float(value)
            for room_id, value in levels.items()
            if isinstance(value, (int, float)) and math.isfinite(value)
        }

    def invalidate(self) -> None:
        """Forget the level so the next cycle seeds it from the series again.

        An import that rewrites a series end to end rebuilds its absolute
        sums, which leaves a level captured beforehand describing values that
        no longer exist. Forcing it back in would land the whole difference on
        one hour.
        """
        self._state["settled_through"] = None
        self._state["levels"] = {}

    def plan(self, now: datetime, zone: ZoneInfo) -> RebasePlan | None:
        """Days to add to reach the settled day, or None when up to date.

        Returns None past MAX_CATCH_UP_DAYS as well: the caller re-seeds then,
        because replaying that long would widen the hourly window to match.
        """
        through = self.settled_through
        target = settled_day(now, zone)
        if through is None or through >= target:
            return None
        first = through + timedelta(days=1)
        if (target - first).days + 1 > MAX_CATCH_UP_DAYS:
            return None
        return RebasePlan(
            first=first,
            last=target,
            begin=int(local_midnight(first, zone).timestamp()),
            end=int(local_midnight(target + timedelta(days=1), zone).timestamp()),
        )

    def needs_reseed(self, now: datetime, zone: ZoneInfo) -> bool:
        """True when no level is known, or the lag exceeds what we replay."""
        through = self.settled_through
        if through is None:
            return True
        target = settled_day(now, zone)
        return (target - through).days > MAX_CATCH_UP_DAYS

    def advance(self, through: date, added: Mapping[str, float]) -> None:
        """Add one catch-up's kWh per room and mark the day settled.

        Committed only by the caller, after every room's measures were read:
        a partial advance would understate the level for the rooms it skipped.
        """
        levels = self._state["levels"]
        for room_id, kwh in added.items():
            if not isinstance(kwh, (int, float)) or not math.isfinite(kwh) or kwh < 0:
                raise ValueError(f"Invalid rebase total for room {room_id}")
            levels[room_id] = round(float(levels.get(room_id, 0.0)) + float(kwh), 3)
        self._state["settled_through"] = through.isoformat()

    def hourly_start(self, zone: ZoneInfo) -> int | None:
        """First second the hourly pass must cover: midnight after the level."""
        through = self.settled_through
        if through is None:
            return None
        return int(local_midnight(through + timedelta(days=1), zone).timestamp())
