"""Tests for IntuisHome entity."""
from __future__ import annotations

import pytest
from typing import Any

from custom_components.intuis_connect.entity.intuis_home import IntuisHome, Capability


# ---------------------------------------------------------------------------
# Test: Capability
# ---------------------------------------------------------------------------

class TestCapability:
    """Tests for Capability dataclass."""

    def test_from_dict_with_all_fields(self):
        """from_dict creates Capability with all fields."""
        data = {"name": "thermostat", "available": True}
        result = Capability.from_dict(data)
        assert result.name == "thermostat"
        assert result.available is True

    def test_from_dict_missing_name_uses_default(self):
        """from_dict uses empty string for missing name."""
        data = {"available": True}
        result = Capability.from_dict(data)
        assert result.name == ""

    def test_from_dict_missing_available_uses_default(self):
        """from_dict uses False for missing available."""
        data = {"name": "thermostat"}
        result = Capability.from_dict(data)
        assert result.available is False


# ---------------------------------------------------------------------------
# Test: IntuisHome.from_api
# ---------------------------------------------------------------------------

class TestIntuisHomeFromApi:
    """Tests for IntuisHome.from_api factory method."""

    @pytest.fixture
    def minimal_home_data(self) -> dict[str, Any]:
        """Minimal valid home data."""
        return {
            "id": "home_123",
            "name": "My Home",
            "rooms": [],
        }

    @pytest.fixture
    def complete_home_data(self) -> dict[str, Any]:
        """Complete home data with all fields."""
        return {
            "id": "home_123",
            "name": "My Home",
            "country": "FR",
            "timezone": "Europe/Paris",
            "coordinates": [2.3522, 48.8566],
            "altitude": 35,
            "city": "Paris",
            "currency_code": "EUR",
            "nb_users": 2,
            "capabilities": [{"name": "thermostat", "available": True}],
            "temperature_control_mode": "heating",
            "therm_mode": "schedule",
            "therm_setpoint_default_duration": 120,
            "therm_heating_priority": "comfort",
            "anticipation": True,
            "rooms": [
                {"id": "room_1", "name": "Living Room", "type": "livingroom", "module_ids": []}
            ],
            "schedules": [],
        }

    def test_from_api_with_complete_data(self, complete_home_data):
        """from_api creates IntuisHome with all fields populated."""
        result = IntuisHome.from_api(complete_home_data)

        assert result.id == "home_123"
        assert result.name == "My Home"
        assert result.country == "FR"
        assert result.timezone == "Europe/Paris"
        assert result.coordinates == (2.3522, 48.8566)
        assert result.altitude == 35
        assert result.city == "Paris"

    def test_from_api_missing_country_uses_none(self, minimal_home_data):
        """from_api uses None when country is missing."""
        result = IntuisHome.from_api(minimal_home_data)
        assert result.country is None

    def test_from_api_missing_timezone_uses_none(self, minimal_home_data):
        """from_api uses None when timezone is missing."""
        result = IntuisHome.from_api(minimal_home_data)
        assert result.timezone is None

    def test_from_api_missing_coordinates_uses_none(self, minimal_home_data):
        """from_api uses None when coordinates is missing."""
        result = IntuisHome.from_api(minimal_home_data)
        assert result.coordinates is None

    def test_from_api_invalid_coordinates_uses_none(self, minimal_home_data):
        """from_api uses None when coordinates is malformed."""
        minimal_home_data["coordinates"] = [1.0]  # Only one value
        result = IntuisHome.from_api(minimal_home_data)
        assert result.coordinates is None

    def test_from_api_missing_optional_fields(self, minimal_home_data):
        """from_api handles missing optional fields gracefully."""
        result = IntuisHome.from_api(minimal_home_data)

        assert result.altitude is None
        assert result.city is None
        assert result.currency_code is None
        assert result.nb_users is None
        assert result.capabilities == []
        assert result.temperature_control_mode is None
        assert result.therm_mode is None

    def test_from_api_parses_rooms(self, minimal_home_data):
        """from_api parses rooms into IntuisRoomDefinition objects."""
        minimal_home_data["rooms"] = [
            {"id": "room_1", "name": "Living Room", "type": "livingroom", "module_ids": []}
        ]
        result = IntuisHome.from_api(minimal_home_data)

        assert "room_1" in result.rooms
        assert result.rooms["room_1"].name == "Living Room"

    def test_from_api_parses_capabilities(self, minimal_home_data):
        """from_api parses capabilities list."""
        minimal_home_data["capabilities"] = [
            {"name": "thermostat", "available": True},
            {"name": "pilot_wire", "available": False},
        ]
        result = IntuisHome.from_api(minimal_home_data)

        assert len(result.capabilities) == 2
        assert result.capabilities[0].name == "thermostat"
        assert result.capabilities[1].available is False


# ---------------------------------------------------------------------------
# Test: IntuisHome Properties
# ---------------------------------------------------------------------------

class TestIntuisHomeProperties:
    """Tests for IntuisHome property accessors."""

    def test_lon_returns_first_coordinate(self):
        """lon property returns longitude (first coordinate)."""
        home = IntuisHome(
            id="home_123",
            name="Test",
            coordinates=(2.3522, 48.8566),
            country="FR",
            timezone="Europe/Paris",
        )
        assert home.lon == 2.3522

    def test_lat_returns_second_coordinate(self):
        """lat property returns latitude (second coordinate)."""
        home = IntuisHome(
            id="home_123",
            name="Test",
            coordinates=(2.3522, 48.8566),
            country="FR",
            timezone="Europe/Paris",
        )
        assert home.lat == 48.8566


# ---------------------------------------------------------------------------
# Test: IntuisHome String Representations
# ---------------------------------------------------------------------------

class TestIntuisHomeStringRepresentation:
    """Tests for IntuisHome __repr__ and __str__."""

    def test_repr_includes_key_info(self):
        """__repr__ includes id, name, room count, and timezone."""
        home = IntuisHome(
            id="home_123",
            name="My Home",
            coordinates=(2.3522, 48.8566),
            country="FR",
            timezone="Europe/Paris",
            rooms={"r1": None, "r2": None},
            schedules=[],
        )
        repr_str = repr(home)

        assert "home_123" in repr_str
        assert "My Home" in repr_str
        assert "rooms=2" in repr_str
        assert "Europe/Paris" in repr_str

    def test_str_returns_name_and_id(self):
        """__str__ returns name (id) format."""
        home = IntuisHome(
            id="home_123",
            name="My Home",
            coordinates=None,
            country=None,
            timezone=None,
        )
        assert str(home) == "My Home (home_123)"
