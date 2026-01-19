"""Tests for IntuisSchedule entities."""
from __future__ import annotations

import pytest
from typing import Any

from custom_components.intuis_connect.entity.intuis_schedule import (
    IntuisSchedule,
    IntuisScheduleRoom,
    IntuisRoomTemperature,
    IntuisThermZone,
    IntuisElectricityZone,
    IntuisEventZone,
    IntuisTimetable,
    IntuisThermSchedule,
    IntuisElectricitySchedule,
    IntuisEventSchedule,
)


# ---------------------------------------------------------------------------
# Test: IntuisRoomTemperature
# ---------------------------------------------------------------------------

class TestIntuisRoomTemperature:
    """Tests for IntuisRoomTemperature.from_dict."""

    def test_from_dict_with_valid_data(self):
        """from_dict creates object with valid data."""
        data = {"room_id": "r1", "temp": 20}
        result = IntuisRoomTemperature.from_dict(data)
        assert result.room_id == "r1"
        assert result.temp == 20

    def test_from_dict_missing_temp_returns_none(self):
        """from_dict returns None when temp is missing."""
        data = {"room_id": "r1"}
        result = IntuisRoomTemperature.from_dict(data)
        assert result is None

    def test_from_dict_missing_room_id_returns_none(self):
        """from_dict returns None when room_id is missing."""
        data = {"temp": 20}
        result = IntuisRoomTemperature.from_dict(data)
        assert result is None

    def test_from_dict_empty_dict_returns_none(self):
        """from_dict returns None for empty dict."""
        result = IntuisRoomTemperature.from_dict({})
        assert result is None


# ---------------------------------------------------------------------------
# Test: IntuisScheduleRoom
# ---------------------------------------------------------------------------

class TestIntuisScheduleRoom:
    """Tests for IntuisScheduleRoom.from_dict."""

    def test_from_dict_with_valid_data(self):
        """from_dict creates object with valid data."""
        data = {"id": "room_1", "therm_setpoint_temperature": 21.0}
        result = IntuisScheduleRoom.from_dict(data)
        assert result.id == "room_1"
        assert result.therm_setpoint_temperature == 21.0

    def test_from_dict_with_preset_mode(self):
        """from_dict handles preset mode correctly."""
        data = {"id": "room_1", "therm_setpoint_fp": "comfort"}
        result = IntuisScheduleRoom.from_dict(data)
        assert result.id == "room_1"
        assert result.therm_setpoint_fp == "comfort"
        assert result.is_preset_mode is True

    def test_from_dict_missing_id_returns_none(self):
        """from_dict returns None when id is missing."""
        data = {"therm_setpoint_temperature": 21.0}
        result = IntuisScheduleRoom.from_dict(data)
        assert result is None

    def test_from_dict_empty_dict_returns_none(self):
        """from_dict returns None for empty dict."""
        result = IntuisScheduleRoom.from_dict({})
        assert result is None


# ---------------------------------------------------------------------------
# Test: IntuisThermZone
# ---------------------------------------------------------------------------

class TestIntuisThermZone:
    """Tests for IntuisThermZone.from_dict."""

    def test_from_dict_with_valid_data(self):
        """from_dict creates object with valid data."""
        data = {
            "id": 1,
            "name": "Comfort",
            "type": 1,
            "rooms_temp": [{"room_id": "r1", "temp": 20}],
            "rooms": [{"id": "r1", "therm_setpoint_temperature": 21.0}],
        }
        result = IntuisThermZone.from_dict(data, "therm")
        assert result.id == 1
        assert result.name == "Comfort"

    def test_from_dict_missing_id_returns_none(self):
        """from_dict returns None when id is missing."""
        data = {"name": "Comfort", "type": 1}
        result = IntuisThermZone.from_dict(data, "therm")
        assert result is None

    def test_from_dict_empty_dict_returns_none(self):
        """from_dict returns None for empty dict."""
        result = IntuisThermZone.from_dict({}, "therm")
        assert result is None

    def test_from_dict_skips_malformed_rooms_temp(self):
        """from_dict skips malformed rooms_temp entries."""
        data = {
            "id": 1,
            "name": "Comfort",
            "rooms_temp": [
                {"room_id": "r1", "temp": 20},  # valid
                {"room_id": "r2"},  # missing temp
            ],
            "rooms": [],
        }
        result = IntuisThermZone.from_dict(data, "therm")
        assert result is not None
        assert len(result.rooms_temp) == 1

    def test_from_dict_skips_malformed_rooms(self):
        """from_dict skips malformed rooms entries."""
        data = {
            "id": 1,
            "name": "Comfort",
            "rooms_temp": [],
            "rooms": [
                {"id": "r1"},  # valid
                {"therm_setpoint_temperature": 21.0},  # missing id
            ],
        }
        result = IntuisThermZone.from_dict(data, "therm")
        assert result is not None
        assert len(result.rooms) == 1


# ---------------------------------------------------------------------------
# Test: IntuisElectricityZone
# ---------------------------------------------------------------------------

class TestIntuisElectricityZone:
    """Tests for IntuisElectricityZone.from_dict."""

    def test_from_dict_with_valid_data(self):
        """from_dict creates object with valid data."""
        data = {"id": 1, "price_type": "peak", "price": 0.25}
        result = IntuisElectricityZone.from_dict(data, "electricity")
        assert result.id == 1
        assert result.price_type == "peak"
        assert result.price == 0.25

    def test_from_dict_missing_id_returns_none(self):
        """from_dict returns None when id is missing."""
        data = {"price_type": "peak", "price": 0.25}
        result = IntuisElectricityZone.from_dict(data, "electricity")
        assert result is None

    def test_from_dict_missing_price_type_returns_none(self):
        """from_dict returns None when price_type is missing."""
        data = {"id": 1, "price": 0.25}
        result = IntuisElectricityZone.from_dict(data, "electricity")
        assert result is None

    def test_from_dict_missing_price_returns_none(self):
        """from_dict returns None when price is missing."""
        data = {"id": 1, "price_type": "peak"}
        result = IntuisElectricityZone.from_dict(data, "electricity")
        assert result is None

    def test_from_dict_empty_dict_returns_none(self):
        """from_dict returns None for empty dict."""
        result = IntuisElectricityZone.from_dict({}, "electricity")
        assert result is None


# ---------------------------------------------------------------------------
# Test: IntuisEventZone
# ---------------------------------------------------------------------------

class TestIntuisEventZone:
    """Tests for IntuisEventZone.from_dict."""

    def test_from_dict_with_valid_data(self):
        """from_dict creates object with valid data."""
        data = {"id": 1, "name": "DHW Schedule", "modules": [{"id": "m1"}]}
        result = IntuisEventZone.from_dict(data, "event")
        assert result.id == 1
        assert result.name == "DHW Schedule"
        assert len(result.modules) == 1

    def test_from_dict_missing_id_returns_none(self):
        """from_dict returns None when id is missing."""
        data = {"name": "DHW Schedule"}
        result = IntuisEventZone.from_dict(data, "event")
        assert result is None

    def test_from_dict_uses_default_name(self):
        """from_dict uses default name when name is missing."""
        data = {"id": 1}
        result = IntuisEventZone.from_dict(data, "event")
        assert result is not None
        assert result.name == "Zone 1"

    def test_from_dict_empty_dict_returns_none(self):
        """from_dict returns None for empty dict."""
        result = IntuisEventZone.from_dict({}, "event")
        assert result is None


# ---------------------------------------------------------------------------
# Test: IntuisTimetable
# ---------------------------------------------------------------------------

class TestIntuisTimetable:
    """Tests for IntuisTimetable.from_dict."""

    def test_from_dict_with_valid_data(self):
        """from_dict creates object with valid data."""
        data = {"zone_id": 1, "m_offset": 420}
        result = IntuisTimetable.from_dict(data)
        assert result.zone_id == 1
        assert result.m_offset == 420

    def test_from_dict_missing_zone_id_returns_none(self):
        """from_dict returns None when zone_id is missing."""
        data = {"m_offset": 420}
        result = IntuisTimetable.from_dict(data)
        assert result is None

    def test_from_dict_missing_m_offset_returns_none(self):
        """from_dict returns None when m_offset is missing."""
        data = {"zone_id": 1}
        result = IntuisTimetable.from_dict(data)
        assert result is None

    def test_from_dict_empty_dict_returns_none(self):
        """from_dict returns None for empty dict."""
        result = IntuisTimetable.from_dict({})
        assert result is None


# ---------------------------------------------------------------------------
# Test: IntuisSchedule.from_dict
# ---------------------------------------------------------------------------

class TestIntuisScheduleFromDict:
    """Tests for IntuisSchedule.from_dict."""

    @pytest.fixture
    def valid_therm_schedule_data(self) -> dict[str, Any]:
        """Valid therm schedule data."""
        return {
            "id": "schedule_123",
            "name": "Weekly Schedule",
            "type": "therm",
            "default": True,
            "selected": True,
            "away_temp": 14,
            "hg_temp": 7,
            "timetable": [{"zone_id": 1, "m_offset": 0}],
            "zones": [{"id": 1, "name": "Comfort", "type": 1, "rooms_temp": [], "rooms": []}],
        }

    @pytest.fixture
    def valid_electricity_schedule_data(self) -> dict[str, Any]:
        """Valid electricity schedule data."""
        return {
            "id": "elec_123",
            "name": "Peak/Off-peak",
            "type": "electricity",
            "default": False,
            "selected": True,
            "tariff": "tempo",
            "tariff_option": "base",
            "timetable": [],
            "zones": [{"id": 1, "price_type": "peak", "price": 0.25}],
        }

    @pytest.fixture
    def valid_event_schedule_data(self) -> dict[str, Any]:
        """Valid event schedule data."""
        return {
            "id": "event_123",
            "name": "DHW Schedule",
            "type": "event",
            "default": False,
            "selected": True,
            "timetable": [],
            "zones": [{"id": 1, "name": "Zone 1"}],
        }

    def test_from_dict_creates_therm_schedule(self, valid_therm_schedule_data):
        """from_dict creates IntuisThermSchedule for therm type."""
        result = IntuisSchedule.from_dict(valid_therm_schedule_data)
        assert isinstance(result, IntuisThermSchedule)
        assert result.id == "schedule_123"
        assert result.away_temp == 14

    def test_from_dict_creates_electricity_schedule(self, valid_electricity_schedule_data):
        """from_dict creates IntuisElectricitySchedule for electricity type."""
        result = IntuisSchedule.from_dict(valid_electricity_schedule_data)
        assert isinstance(result, IntuisElectricitySchedule)
        assert result.tariff == "tempo"

    def test_from_dict_creates_event_schedule(self, valid_event_schedule_data):
        """from_dict creates IntuisEventSchedule for event type."""
        result = IntuisSchedule.from_dict(valid_event_schedule_data)
        assert isinstance(result, IntuisEventSchedule)
        assert result.name == "DHW Schedule"

    def test_from_dict_missing_type_returns_none(self):
        """from_dict returns None when type is missing."""
        data = {"id": "schedule_123", "name": "Test"}
        result = IntuisSchedule.from_dict(data)
        assert result is None

    def test_from_dict_invalid_type_returns_none(self):
        """from_dict returns None for invalid type."""
        data = {"id": "schedule_123", "name": "Test", "type": "unknown"}
        result = IntuisSchedule.from_dict(data)
        assert result is None

    def test_from_dict_skips_malformed_zones(self, valid_therm_schedule_data):
        """from_dict skips malformed zone entries."""
        valid_therm_schedule_data["zones"] = [
            {"id": 1, "name": "Good Zone"},  # valid
            {"name": "No ID Zone"},  # missing id - should be skipped
        ]
        result = IntuisSchedule.from_dict(valid_therm_schedule_data)
        assert result is not None
        assert len(result.zones) == 1

    def test_from_dict_skips_malformed_timetables(self, valid_therm_schedule_data):
        """from_dict skips malformed timetable entries."""
        valid_therm_schedule_data["timetable"] = [
            {"zone_id": 1, "m_offset": 0},  # valid
            {"zone_id": 2},  # missing m_offset - should be skipped
        ]
        result = IntuisSchedule.from_dict(valid_therm_schedule_data)
        assert result is not None
        assert len(result.timetables) == 1

    def test_from_dict_handles_empty_zones(self, valid_therm_schedule_data):
        """from_dict handles empty zones list."""
        valid_therm_schedule_data["zones"] = []
        result = IntuisSchedule.from_dict(valid_therm_schedule_data)
        assert result is not None
        assert result.zones == []

    def test_from_dict_uses_default_values(self):
        """from_dict uses default values for optional fields."""
        data = {
            "id": "schedule_123",
            "type": "therm",
        }
        result = IntuisSchedule.from_dict(data)
        assert result is not None
        assert result.default is False
        assert result.selected is False
