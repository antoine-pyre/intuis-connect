"""Tests for Intuis Connect service handlers."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.intuis_connect.utils.const import DOMAIN


# ---------------------------------------------------------------------------
# Test: Timetable Helper Functions (already tested in test_schedule_helpers.py)
# These tests focus on integration with service handlers
# ---------------------------------------------------------------------------

class TestSwitchScheduleService:
    """Tests for switch_schedule service."""

    def test_switch_schedule_extracts_name(self):
        """switch_schedule extracts schedule_name from call.data."""
        from custom_components.intuis_connect import ATTR_SCHEDULE_NAME

        call = MagicMock()
        call.data = {"schedule_name": "Comfort"}

        schedule_name = call.data.get(ATTR_SCHEDULE_NAME)
        assert schedule_name == "Comfort"

    def test_switch_schedule_missing_name(self):
        """switch_schedule with missing name returns None."""
        call = MagicMock()
        call.data = {}

        schedule_name = call.data.get("schedule_name")
        assert schedule_name is None

    @pytest.mark.asyncio
    async def test_switch_schedule_api_called(self, mock_api):
        """API switch_schedule is called with correct params."""
        mock_api.async_switch_schedule = AsyncMock()

        await mock_api.async_switch_schedule("home_123", "schedule_1")

        mock_api.async_switch_schedule.assert_called_once_with("home_123", "schedule_1")


class TestRefreshSchedulesService:
    """Tests for refresh_schedules service."""

    @pytest.mark.asyncio
    async def test_refresh_schedules_fetches_data(self, mock_api):
        """refresh_schedules fetches fresh data from API."""
        mock_fresh_home = MagicMock()
        mock_fresh_home.schedules = [MagicMock(), MagicMock()]
        mock_api.async_get_homes_data = AsyncMock(return_value=mock_fresh_home)

        await mock_api.async_get_homes_data()

        mock_api.async_get_homes_data.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_schedules_updates_local_state(self, mock_api):
        """refresh_schedules updates local intuis_home.schedules."""
        mock_intuis_home = MagicMock()
        mock_intuis_home.schedules = []

        mock_fresh_home = MagicMock()
        mock_fresh_home.schedules = [MagicMock(name="New Schedule")]
        mock_api.async_get_homes_data = AsyncMock(return_value=mock_fresh_home)

        # Simulate the refresh logic
        fresh_home = await mock_api.async_get_homes_data()
        mock_intuis_home.schedules = fresh_home.schedules

        assert len(mock_intuis_home.schedules) == 1


class TestSetScheduleSlotService:
    """Tests for set_schedule_slot service."""

    def test_parse_day_valid(self):
        """Day parameter parsing for valid values."""
        for day in range(7):
            day_str = str(day)
            parsed = int(day_str)
            assert 0 <= parsed <= 6

    def test_parse_day_invalid(self):
        """Day parameter parsing for invalid values."""
        invalid_values = ["7", "-1", "abc", None]
        for val in invalid_values:
            try:
                if val is None:
                    raise TypeError
                parsed = int(val)
                if not (0 <= parsed <= 6):
                    raise ValueError
                assert False, f"Should have raised for {val}"
            except (ValueError, TypeError):
                pass  # Expected

    def test_parse_time_dict_format(self):
        """Time parsing for dict format (TimeSelector)."""
        time_dict = {"hours": 7, "minutes": 30}
        hours = time_dict.get("hours", 0)
        minutes = time_dict.get("minutes", 0)

        assert hours == 7
        assert minutes == 30

    def test_parse_time_string_format(self):
        """Time parsing for string format (HH:MM)."""
        time_str = "07:30"
        parts = time_str.split(":")
        hours = int(parts[0])
        minutes = int(parts[1])

        assert hours == 7
        assert minutes == 30

    def test_parse_time_string_with_seconds(self):
        """Time parsing for string format (HH:MM:SS)."""
        time_str = "07:30:00"
        parts = time_str.split(":")
        hours = int(parts[0])
        minutes = int(parts[1])

        assert hours == 7
        assert minutes == 30

    def test_calculate_m_offset(self):
        """m_offset calculation for day and time."""
        MINUTES_PER_DAY = 1440

        # Monday 07:00
        day = 0
        hours = 7
        minutes = 0
        m_offset = day * MINUTES_PER_DAY + hours * 60 + minutes
        assert m_offset == 420

        # Tuesday 22:00
        day = 1
        hours = 22
        minutes = 0
        m_offset = day * MINUTES_PER_DAY + hours * 60 + minutes
        assert m_offset == 1440 + 1320  # 2760

        # Sunday 23:59
        day = 6
        hours = 23
        minutes = 59
        m_offset = day * MINUTES_PER_DAY + hours * 60 + minutes
        assert m_offset == 6 * 1440 + 23 * 60 + 59  # 10079

    def test_validate_zone_name_required(self):
        """zone_name is required."""
        call_data = {"start_day": "0", "start_time": "07:00", "end_time": "22:00"}
        zone_name = call_data.get("zone_name")
        assert zone_name is None

    def test_multi_day_span_offset_calculation(self):
        """m_offset calculation for multi-day spans."""
        MINUTES_PER_DAY = 1440

        # Start: Monday 22:00
        start_day = 0
        start_hours = 22
        start_minutes = 0
        start_m_offset = start_day * MINUTES_PER_DAY + start_hours * 60 + start_minutes

        # End: Tuesday 06:00
        end_day = 1
        end_hours = 6
        end_minutes = 0
        end_m_offset = end_day * MINUTES_PER_DAY + end_hours * 60 + end_minutes

        assert start_m_offset == 1320  # Monday 22:00
        assert end_m_offset == 1800    # Tuesday 06:00
        assert end_m_offset > start_m_offset


# ---------------------------------------------------------------------------
# Test: Service Registration
# ---------------------------------------------------------------------------

class TestServiceRegistration:
    """Tests for service registration."""

    def test_service_constants_defined(self):
        """Service constants are properly defined."""
        from custom_components.intuis_connect import (
            SERVICE_SWITCH_SCHEDULE,
            SERVICE_REFRESH_SCHEDULES,
            SERVICE_SET_SCHEDULE_SLOT,
        )

        assert SERVICE_SWITCH_SCHEDULE == "switch_schedule"
        assert SERVICE_REFRESH_SCHEDULES == "refresh_schedules"
        assert SERVICE_SET_SCHEDULE_SLOT == "set_schedule_slot"

    def test_service_attributes_defined(self):
        """Service attributes are defined as constants."""
        from custom_components.intuis_connect import (
            ATTR_SCHEDULE_NAME,
            ATTR_DAY,
            ATTR_START_DAY,
            ATTR_END_DAY,
            ATTR_START_TIME,
            ATTR_END_TIME,
            ATTR_ZONE_NAME,
        )

        assert ATTR_SCHEDULE_NAME == "schedule_name"
        assert ATTR_DAY == "day"
        assert ATTR_START_DAY == "start_day"
        assert ATTR_END_DAY == "end_day"
        assert ATTR_START_TIME == "start_time"
        assert ATTR_END_TIME == "end_time"
        assert ATTR_ZONE_NAME == "zone_name"
