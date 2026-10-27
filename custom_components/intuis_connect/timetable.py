"""Timetable manipulation helpers for schedule management.

This module provides utility functions for working with Intuis heating schedule
timetables, including zone lookup, entry insertion, and duplicate removal.
"""

from __future__ import annotations

import logging

_LOGGER = logging.getLogger(__name__)

# Day constants for readability
DAYS_OF_WEEK = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]
DAYS_OF_WEEK_LABELS = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]
MINUTES_PER_DAY = 1440


def find_zone_at_offset(timetable: list[dict], m_offset: int) -> int:
    """Find which zone is active at a given minute offset.

    Looks backwards through the sorted timetable to find the most recent zone
    that starts at or before the given offset.

    Args:
        timetable: List of timetable entries, each with 'm_offset' and 'zone_id' keys.
        m_offset: The minute offset from Monday 00:00 (0-10079).

    Returns:
        The zone_id active at the given offset.
        Returns 0 if timetable is empty, or the last zone if offset is before
        the first entry (week wrap-around).
    """
    if not timetable:
        return 0  # Default fallback

    sorted_tt = sorted(timetable, key=lambda x: x["m_offset"])

    # Default to last zone (for wrap-around from end of week)
    result_zone = sorted_tt[-1]["zone_id"]

    for entry in sorted_tt:
        if entry["m_offset"] <= m_offset:
            result_zone = entry["zone_id"]
        else:
            break

    return result_zone


def upsert_timetable_entry(timetable: list[dict], m_offset: int, zone_id: int) -> None:
    """Update existing entry or insert new one at the given offset.

    If an entry already exists at the specified m_offset, its zone_id is updated.
    Otherwise, a new entry is appended to the timetable.

    Args:
        timetable: List of timetable entries to modify (mutated in place).
        m_offset: The minute offset for the entry (0-10079).
        zone_id: The zone ID to set at this offset.
    """
    for entry in timetable:
        if entry["m_offset"] == m_offset:
            entry["zone_id"] = zone_id
            return
    timetable.append({"zone_id": zone_id, "m_offset": m_offset})


def remove_consecutive_duplicates(timetable: list[dict]) -> list[dict]:
    """Remove consecutive entries with the same zone_id.

    The Intuis API rejects timetables with consecutive entries having the same
    zone_id. This function removes such duplicates while preserving the first
    occurrence.

    Args:
        timetable: List of timetable entries to process.

    Returns:
        A new list with consecutive duplicates removed, sorted by m_offset.
    """
    if not timetable:
        return []

    sorted_tt = sorted(timetable, key=lambda x: x["m_offset"])
    result = [sorted_tt[0]]

    for entry in sorted_tt[1:]:
        if entry["zone_id"] != result[-1]["zone_id"]:
            result.append(entry)
        else:
            _LOGGER.debug(
                "Removing duplicate zone_id %d at m_offset %d",
                entry["zone_id"],
                entry["m_offset"],
            )

    return result


def calculate_m_offset(day: int, hours: int, minutes: int) -> int:
    """Calculate minute offset from day and time.

    Args:
        day: Day of week (0=Monday, 6=Sunday).
        hours: Hour of day (0-23).
        minutes: Minute of hour (0-59).

    Returns:
        The minute offset from Monday 00:00 (0-10079).
    """
    return day * MINUTES_PER_DAY + hours * 60 + minutes


def parse_time_string(time_str: str) -> tuple[int, int]:
    """Parse a time string in HH:MM or HH:MM:SS format.

    Args:
        time_str: Time string to parse.

    Returns:
        Tuple of (hours, minutes).

    Raises:
        ValueError: If the time string is invalid.
    """
    parts = time_str.split(":")
    if len(parts) < 2:
        raise ValueError(f"Invalid time format: {time_str}")
    return int(parts[0]), int(parts[1])


def parse_time_value(time_value: dict | str) -> tuple[int, int]:
    """Parse a time value from either dict or string format.

    Handles both TimeSelector dict format and HH:MM string format.

    Args:
        time_value: Either a dict with 'hours'/'minutes' keys, or a time string.

    Returns:
        Tuple of (hours, minutes).

    Raises:
        ValueError: If the time value cannot be parsed.
    """
    if isinstance(time_value, dict):
        return time_value.get("hours", 0), time_value.get("minutes", 0)
    return parse_time_string(str(time_value))


MINUTES_PER_WEEK = 7 * MINUTES_PER_DAY


def replace_timetable_interval(
    timetable: list[dict],
    start: int,
    end: int,
    zone_id: int,
) -> list[dict]:
    """Replace [start, end) on a cyclic week, without changing its complement.

    End may be 10080 for Sunday midnight. Equal normalized bounds are ambiguous
    (empty vs a full week) and rejected. The input is never modified.
    """
    if (
        isinstance(start, bool)
        or isinstance(end, bool)
        or not isinstance(start, int)
        or not isinstance(end, int)
        or not 0 <= start < MINUTES_PER_WEEK
        or not 0 <= end <= MINUTES_PER_WEEK
    ):
        raise ValueError("Schedule offsets must be integer minutes within the week")
    end %= MINUTES_PER_WEEK
    duration = (end - start) % MINUTES_PER_WEEK
    if not duration:
        raise ValueError(
            "A schedule interval must have distinct start and end boundaries"
        )
    if not timetable:
        raise ValueError("Cannot edit a schedule without timetable entries")
    original = []
    offsets = set()
    for entry in timetable:
        offset = entry["m_offset"]
        if (
            isinstance(offset, bool)
            or not isinstance(offset, int)
            or not 0 <= offset < MINUTES_PER_WEEK
            or offset in offsets
        ):
            raise ValueError(
                "Existing timetable offsets must be unique integer minutes within the week"
            )
        offsets.add(offset)
        original.append({"m_offset": offset, "zone_id": entry["zone_id"]})
    restore_zone = find_zone_at_offset(original, end)
    updated = [
        entry
        for entry in original
        if (entry["m_offset"] - start) % MINUTES_PER_WEEK >= duration
    ]
    upsert_timetable_entry(updated, start, zone_id)
    upsert_timetable_entry(updated, end, restore_zone)
    return remove_consecutive_duplicates(updated)


def schedule_slot_offsets(
    start_day: int | str,
    start_time: str | dict,
    end_day: int | str,
    end_time: str | dict,
) -> tuple[int, int]:
    """Validate minute-precision service inputs, keeping same-day midnight semantics."""

    def day_value(value):
        if isinstance(value, bool) or str(value) not in {str(day) for day in range(7)}:
            raise ValueError("Days must be integers from 0 (Monday) to 6 (Sunday)")
        return int(value)

    def clock_value(value):
        if isinstance(value, dict):
            parts = [
                value.get("hours", 0),
                value.get("minutes", 0),
                value.get("seconds", 0),
            ]
        elif isinstance(value, str) and len(value.split(":")) in (2, 3):
            parts = value.split(":")
            if len(parts) == 2:
                parts.append("0")
        else:
            raise ValueError("Time must use HH:MM or HH:MM:00")
        if any(
            isinstance(part, bool)
            or not (isinstance(part, int) or isinstance(part, str) and part.isdecimal())
            for part in parts
        ):
            raise ValueError("Time must use integer hours and minutes")
        hours, minutes, seconds = (int(part) for part in parts)
        if not (0 <= hours < 24 and 0 <= minutes < 60 and seconds == 0):
            raise ValueError("Time must be a valid clock time with zero seconds")
        return hours, minutes

    first, last = day_value(start_day), day_value(end_day)
    sh, sm = clock_value(start_time)
    eh, em = clock_value(end_time)
    start = calculate_m_offset(first, sh, sm)
    end = calculate_m_offset(last, eh, em)
    if first == last and eh == em == 0:
        end = (last + 1) * MINUTES_PER_DAY
    if first == last and end <= start:
        raise ValueError("End must be after start on the same day")
    if start % MINUTES_PER_WEEK == end % MINUTES_PER_WEEK:
        raise ValueError(
            "A schedule interval must have distinct start and end boundaries"
        )
    return start, end
