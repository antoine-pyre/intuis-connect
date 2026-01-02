"""Tests for schedule timetable helper functions."""
from __future__ import annotations

import pytest

# Import the functions under test
from custom_components.intuis_connect.timetable import (
    find_zone_at_offset,
    upsert_timetable_entry,
    remove_consecutive_duplicates,
)


# ---------------------------------------------------------------------------
# Test: _find_zone_at_offset
# ---------------------------------------------------------------------------

class TestFindZoneAtOffset:
    """Tests for finding active zone at a given time offset."""

    def test_empty_timetable_returns_zero(self):
        """Empty timetable should return 0 as fallback."""
        assert find_zone_at_offset([], 420) == 0

    def test_exact_match_returns_zone(self):
        """Exact match on m_offset should return that zone."""
        timetable = [
            {"m_offset": 0, "zone_id": 1},
            {"m_offset": 420, "zone_id": 2},
            {"m_offset": 1320, "zone_id": 1},
        ]
        assert find_zone_at_offset(timetable, 420) == 2

    def test_between_entries_returns_previous_zone(self):
        """Offset between entries should return the previous (most recent) zone."""
        timetable = [
            {"m_offset": 0, "zone_id": 1},
            {"m_offset": 420, "zone_id": 2},
            {"m_offset": 1320, "zone_id": 1},
        ]
        # 600 is between 420 and 1320, so zone 2 should be active
        assert find_zone_at_offset(timetable, 600) == 2

    def test_before_first_entry_wraps_to_end(self):
        """Offset before first entry should wrap to last zone of week."""
        timetable = [
            {"m_offset": 420, "zone_id": 2},
            {"m_offset": 1320, "zone_id": 1},
        ]
        # Offset 0 is before first entry (420), should wrap to zone 1
        assert find_zone_at_offset(timetable, 0) == 1

    def test_at_start_of_week(self):
        """Offset 0 with entry at 0 should return that zone."""
        timetable = [
            {"m_offset": 0, "zone_id": 3},
            {"m_offset": 420, "zone_id": 2},
        ]
        assert find_zone_at_offset(timetable, 0) == 3

    def test_unsorted_timetable_handled(self):
        """Unsorted timetable should be handled correctly."""
        timetable = [
            {"m_offset": 1320, "zone_id": 1},
            {"m_offset": 0, "zone_id": 3},
            {"m_offset": 420, "zone_id": 2},
        ]
        # Function sorts internally
        assert find_zone_at_offset(timetable, 600) == 2

    def test_end_of_week(self):
        """Offset at end of week should return last active zone."""
        timetable = [
            {"m_offset": 0, "zone_id": 1},
            {"m_offset": 420, "zone_id": 2},
            {"m_offset": 1320, "zone_id": 3},
        ]
        # Sunday 23:59 = 6 * 1440 + 23*60 + 59 = 10079
        assert find_zone_at_offset(timetable, 10079) == 3


# ---------------------------------------------------------------------------
# Test: _upsert_timetable_entry
# ---------------------------------------------------------------------------

class TestUpsertTimetableEntry:
    """Tests for upserting timetable entries."""

    def test_insert_into_empty(self):
        """Insert into empty timetable."""
        timetable = []
        upsert_timetable_entry(timetable, 420, 2)
        assert timetable == [{"zone_id": 2, "m_offset": 420}]

    def test_insert_new_entry(self):
        """Insert new entry at offset not yet present."""
        timetable = [
            {"m_offset": 0, "zone_id": 1},
            {"m_offset": 1320, "zone_id": 1},
        ]
        upsert_timetable_entry(timetable, 420, 2)
        assert len(timetable) == 3
        assert {"zone_id": 2, "m_offset": 420} in timetable

    def test_update_existing_entry(self):
        """Update existing entry at same offset."""
        timetable = [
            {"m_offset": 0, "zone_id": 1},
            {"m_offset": 420, "zone_id": 2},
            {"m_offset": 1320, "zone_id": 1},
        ]
        upsert_timetable_entry(timetable, 420, 3)
        assert len(timetable) == 3
        # Find entry with m_offset 420 and verify zone changed
        entry = next(e for e in timetable if e["m_offset"] == 420)
        assert entry["zone_id"] == 3

    def test_update_preserves_other_entries(self):
        """Updating one entry doesn't affect others."""
        timetable = [
            {"m_offset": 0, "zone_id": 1},
            {"m_offset": 420, "zone_id": 2},
            {"m_offset": 1320, "zone_id": 1},
        ]
        upsert_timetable_entry(timetable, 420, 3)

        entry_0 = next(e for e in timetable if e["m_offset"] == 0)
        entry_1320 = next(e for e in timetable if e["m_offset"] == 1320)
        assert entry_0["zone_id"] == 1
        assert entry_1320["zone_id"] == 1


# ---------------------------------------------------------------------------
# Test: _remove_consecutive_duplicates
# ---------------------------------------------------------------------------

class TestRemoveConsecutiveDuplicates:
    """Tests for removing consecutive duplicate zones."""

    def test_empty_timetable(self):
        """Empty timetable returns empty list."""
        assert remove_consecutive_duplicates([]) == []

    def test_single_entry(self):
        """Single entry is returned as-is."""
        timetable = [{"m_offset": 0, "zone_id": 1}]
        result = remove_consecutive_duplicates(timetable)
        assert result == [{"m_offset": 0, "zone_id": 1}]

    def test_no_duplicates(self):
        """No consecutive duplicates, all entries kept."""
        timetable = [
            {"m_offset": 0, "zone_id": 1},
            {"m_offset": 420, "zone_id": 2},
            {"m_offset": 1320, "zone_id": 1},
        ]
        result = remove_consecutive_duplicates(timetable)
        assert len(result) == 3

    def test_consecutive_duplicates_removed(self):
        """Consecutive entries with same zone_id are removed."""
        timetable = [
            {"m_offset": 0, "zone_id": 1},
            {"m_offset": 420, "zone_id": 1},  # Duplicate
            {"m_offset": 1320, "zone_id": 2},
        ]
        result = remove_consecutive_duplicates(timetable)
        assert len(result) == 2
        assert result[0] == {"m_offset": 0, "zone_id": 1}
        assert result[1] == {"m_offset": 1320, "zone_id": 2}

    def test_multiple_consecutive_duplicates(self):
        """Multiple consecutive duplicates are all removed."""
        timetable = [
            {"m_offset": 0, "zone_id": 1},
            {"m_offset": 420, "zone_id": 1},  # Duplicate
            {"m_offset": 840, "zone_id": 1},  # Duplicate
            {"m_offset": 1320, "zone_id": 2},
        ]
        result = remove_consecutive_duplicates(timetable)
        assert len(result) == 2
        assert result[0]["m_offset"] == 0
        assert result[1]["m_offset"] == 1320

    def test_non_consecutive_same_zone_kept(self):
        """Non-consecutive entries with same zone are kept."""
        timetable = [
            {"m_offset": 0, "zone_id": 1},
            {"m_offset": 420, "zone_id": 2},
            {"m_offset": 840, "zone_id": 1},  # Same as first but not consecutive
        ]
        result = remove_consecutive_duplicates(timetable)
        assert len(result) == 3

    def test_unsorted_input_handled(self):
        """Unsorted input is sorted before processing."""
        timetable = [
            {"m_offset": 420, "zone_id": 1},  # Duplicate of 0
            {"m_offset": 0, "zone_id": 1},
            {"m_offset": 1320, "zone_id": 2},
        ]
        result = remove_consecutive_duplicates(timetable)
        assert len(result) == 2
        # First entry should be m_offset 0 after sorting
        assert result[0]["m_offset"] == 0

    def test_all_same_zone(self):
        """All entries with same zone reduces to single entry."""
        timetable = [
            {"m_offset": 0, "zone_id": 1},
            {"m_offset": 420, "zone_id": 1},
            {"m_offset": 840, "zone_id": 1},
            {"m_offset": 1320, "zone_id": 1},
        ]
        result = remove_consecutive_duplicates(timetable)
        assert len(result) == 1
        assert result[0]["m_offset"] == 0


# ---------------------------------------------------------------------------
# Test: Integration of helper functions
# ---------------------------------------------------------------------------

class TestTimetableIntegration:
    """Integration tests using multiple helper functions together."""

    def test_set_slot_workflow(self):
        """Simulate setting a time slot (start and end)."""
        # Initial timetable: Night all day
        timetable = [
            {"m_offset": 0, "zone_id": 1},  # Night from midnight
        ]

        # User wants Comfort (zone 2) from 07:00 to 22:00 on Monday
        start_offset = 420  # Monday 07:00
        end_offset = 1320   # Monday 22:00

        # Find what zone to restore at end
        restore_zone = find_zone_at_offset(timetable, end_offset)
        assert restore_zone == 1  # Night

        # Insert start slot
        upsert_timetable_entry(timetable, start_offset, 2)  # Comfort at 07:00

        # Insert end slot to restore
        upsert_timetable_entry(timetable, end_offset, restore_zone)  # Night at 22:00

        # Clean up duplicates
        result = remove_consecutive_duplicates(timetable)

        assert len(result) == 3
        # Verify schedule: Night -> Comfort -> Night
        sorted_result = sorted(result, key=lambda x: x["m_offset"])
        assert sorted_result[0] == {"m_offset": 0, "zone_id": 1}     # Night
        assert sorted_result[1] == {"m_offset": 420, "zone_id": 2}   # Comfort
        assert sorted_result[2] == {"m_offset": 1320, "zone_id": 1}  # Night

    def test_set_overlapping_slots(self):
        """Setting a slot that overlaps existing slots."""
        # Initial: Night -> Comfort -> Night
        timetable = [
            {"m_offset": 0, "zone_id": 1},
            {"m_offset": 420, "zone_id": 2},
            {"m_offset": 1320, "zone_id": 1},
        ]

        # Set Eco (zone 3) from 12:00 to 14:00
        start_offset = 720   # 12:00
        end_offset = 840     # 14:00

        restore_zone = find_zone_at_offset(timetable, end_offset)
        assert restore_zone == 2  # Comfort is active at 14:00

        upsert_timetable_entry(timetable, start_offset, 3)  # Eco
        upsert_timetable_entry(timetable, end_offset, restore_zone)  # Comfort

        result = remove_consecutive_duplicates(timetable)

        # Should be: Night -> Comfort -> Eco -> Comfort -> Night
        assert len(result) == 5
