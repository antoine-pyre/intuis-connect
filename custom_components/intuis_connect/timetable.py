"""Timetable manipulation helpers for schedule management.

This module provides utility functions for working with Intuis heating schedule
timetables, including zone lookup, entry insertion, and duplicate removal.
"""
from __future__ import annotations

import logging

_LOGGER = logging.getLogger(__name__)

# Day constants for readability
DAYS_OF_WEEK = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
DAYS_OF_WEEK_LABELS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
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
    """Remove duplicate offsets and consecutive entries with the same zone_id.

    The Intuis API requires:
    1. All m_offset values must be STRICTLY INCREASING (no duplicates)
    2. Consecutive entries should not have the same zone_id

    This function:
    1. First removes duplicate m_offset values (keeps the LAST zone_id for each offset)
    2. Then removes consecutive entries with the same zone_id

    Args:
        timetable: List of timetable entries to process.

    Returns:
        A new list with strictly increasing offsets and no consecutive zone duplicates.
    """
    if not timetable:
        return []

    # Step 1: Sort by m_offset
    sorted_tt = sorted(timetable, key=lambda x: x["m_offset"])
    
    # Step 2: Remove duplicate m_offset values (keep the LAST entry for each offset)
    # This handles the case where multiple zones are defined at the same offset
    offset_to_zone: dict[int, int] = {}
    for entry in sorted_tt:
        m_offset = entry["m_offset"]
        zone_id = entry["zone_id"]
        if m_offset in offset_to_zone and offset_to_zone[m_offset] != zone_id:
            _LOGGER.debug(
                "Duplicate m_offset %d: replacing zone_id %d with %d",
                m_offset,
                offset_to_zone[m_offset],
                zone_id,
            )
        offset_to_zone[m_offset] = zone_id
    
    # Step 3: Build list with unique offsets in sorted order
    unique_offsets = sorted(offset_to_zone.keys())
    deduped = [{"zone_id": offset_to_zone[offset], "m_offset": offset} for offset in unique_offsets]
    
    if not deduped:
        return []
    
    # Step 4: Remove consecutive entries with the same zone_id
    result = [deduped[0]]
    for entry in deduped[1:]:
        if entry["zone_id"] != result[-1]["zone_id"]:
            result.append(entry)
        else:
            _LOGGER.debug(
                "Removing consecutive duplicate zone_id %d at m_offset %d",
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


def normalize_timetable(timetable: list[dict]) -> list[dict]:
    """Normalize a timetable to ensure proper coverage for all days.

    This function ensures that:
    1. Each day has a zone defined from its start
    2. Zones are properly inherited from the previous day if no explicit slot exists
    3. Consecutive entries with the same zone_id are merged
    4. No duplicate m_offset values exist (strictly increasing offsets)

    The Intuis API requires a properly normalized timetable to work correctly.

    Args:
        timetable: List of timetable entries, each with 'm_offset' and 'zone_id' keys.

    Returns:
        A new normalized timetable list.
    """
    if not timetable:
        return []

    # First, deduplicate by m_offset (keep last zone for each offset)
    offset_to_zone: dict[int, int] = {}
    for entry in sorted(timetable, key=lambda x: x["m_offset"]):
        offset_to_zone[entry["m_offset"]] = entry["zone_id"]
    
    sorted_tt = [{"m_offset": offset, "zone_id": zone} 
                 for offset, zone in sorted(offset_to_zone.items())]
    
    result = []

    for day in range(7):
        base = day * MINUTES_PER_DAY
        next_day = base + MINUTES_PER_DAY

        # Get slots for this day
        day_slots = [s for s in sorted_tt if base <= s["m_offset"] < next_day]

        # Find the zone that should be active at the start of this day
        # (inherited from previous slots)
        prev_slots = [s for s in sorted_tt if s["m_offset"] < base]
        if prev_slots:
            first_zone = prev_slots[-1]["zone_id"]
        elif day_slots:
            first_zone = day_slots[0]["zone_id"]
        elif sorted_tt:
            first_zone = sorted_tt[0]["zone_id"]
        else:
            first_zone = 0

        # Ensure day starts with a slot if the first slot is not at day start
        if not day_slots or day_slots[0]["m_offset"] > base:
            result.append({"zone_id": first_zone, "m_offset": base})

        # Add all slots for this day
        for slot in day_slots:
            result.append({"zone_id": slot["zone_id"], "m_offset": slot["m_offset"]})

    # Final merge of consecutive same-zone entries
    if not result:
        return []

    merged = [result[0]]
    for entry in result[1:]:
        if entry["zone_id"] != merged[-1]["zone_id"]:
            merged.append(entry)
        else:
            _LOGGER.debug(
                "Normalizing: removing duplicate zone_id %d at m_offset %d",
                entry["zone_id"],
                entry["m_offset"],
            )

    _LOGGER.debug("Normalized timetable: %d entries", len(merged))
    return merged
