from __future__ import annotations

import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)


class IntuisScheduleRoom:
    """Class to represent a room in the Intuis Connect system."""

    def __init__(
        self,
        id: str,
        therm_setpoint_temperature: float | None = None,
        therm_setpoint_fp: str | None = None
    ) -> None:
        """Initialize the room."""
        self.id = id
        self.therm_setpoint_temperature = therm_setpoint_temperature
        self.therm_setpoint_fp = therm_setpoint_fp  # Preset mode: "comfort", "away", etc.

    @property
    def effective_temperature(self) -> float | None:
        """Return the effective temperature (if set directly)."""
        return self.therm_setpoint_temperature

    @property
    def is_preset_mode(self) -> bool:
        """Return True if this room uses a preset mode instead of temperature."""
        return self.therm_setpoint_fp is not None

    @staticmethod
    def from_dict(data: dict[str, Any]) -> IntuisScheduleRoom:
        """Create a room from a dictionary."""
        return IntuisScheduleRoom(
            id=data["id"],
            therm_setpoint_temperature=data.get("therm_setpoint_temperature"),
            therm_setpoint_fp=data.get("therm_setpoint_fp")
        )


class IntuisRoomTemperature:
    """Class to represent a room temperature in the Intuis Connect system."""

    def __init__(self, room_id: str, temp: int) -> None:
        """Initialize the room temperature."""
        self.room_id = room_id
        self.temp = temp

    @staticmethod
    def from_dict(data: dict[str, Any]) -> IntuisRoomTemperature:
        """Create a room temperature from a dictionary."""
        return IntuisRoomTemperature(
            room_id=data["room_id"],
            temp=data["temp"]
        )


class IntuisZone:
    """Base class for zones in the Intuis Connect system."""

    def __init__(self, id: int) -> None:
        """Initialize the zone."""
        self.id = id

    @staticmethod
    def from_dict(data: dict[str, Any], type: str) -> IntuisZone:
        """Create a zone from a dictionary."""
        _LOGGER.debug("Creating IntuisZone from data: %s", data)
        if type is None:
            raise ValueError("Zone type is required")
        if type == "therm":
            return IntuisThermZone.from_dict(data, type)
        if type == "electricity":
            return IntuisElectricityZone.from_dict(data, type)
        if type == "event":
            return IntuisEventZone.from_dict(data, type)


        raise ValueError(f"Unknown zone type: {type}")


class IntuisThermZone(IntuisZone):
    """Class to represent a zone in the Intuis Connect system."""

    def __init__(self, id: int, name: str, type: int,
                 rooms_temp: list[IntuisRoomTemperature],
                 rooms: list[IntuisScheduleRoom]) -> None:
        """Initialize the zone."""
        IntuisZone.__init__(self, id)
        self.name = name
        self.type = type
        self.rooms_temp = rooms_temp
        self.rooms = rooms

    @staticmethod
    def from_dict(data: dict[str, Any], type: str) -> IntuisThermZone:  # noqa: ARG004
        """Create a zone from a dictionary.

        Args:
            data: The zone data dictionary.
            type: The schedule type (unused, but required for interface consistency with IntuisZone.from_dict).
        """
        rooms_temp = [IntuisRoomTemperature.from_dict(rt) for rt in data.get("rooms_temp", [])]
        rooms = [IntuisScheduleRoom.from_dict(r) for r in data.get("rooms", [])]
        return IntuisThermZone(
            id=data["id"],
            name=data.get("name", f"Zone {data['id']}"),
            type=data.get("type", 0),
            rooms_temp=rooms_temp,
            rooms=rooms
        )


class IntuisElectricityZone(IntuisZone):
    """Class to represent a price zone in the Intuis Connect system."""

    def __init__(self, id: int, price_type: str, price: float) -> None:
        """Initialize the price zone."""
        IntuisZone.__init__(self, id)
        self.price_type = price_type
        self.price = price

    @staticmethod
    def from_dict(data: dict[str, Any], type: str) -> IntuisElectricityZone:  # noqa: ARG004
        """Create a price zone from a dictionary.

        Args:
            data: The zone data dictionary.
            type: The schedule type (unused, but required for interface consistency with IntuisZone.from_dict).
        """
        return IntuisElectricityZone(
            id=data["id"],
            price_type=data["price_type"],
            price=data["price"]
        )


class IntuisEventZone(IntuisZone):
    """Class to represent an event zone in the Intuis Connect system."""

    def __init__(self, id: int, name: str,
                 modules: list[dict[str, Any]] | None = None) -> None:
        """Initialize the event zone."""
        IntuisZone.__init__(self, id)
        self.name = name
        self.modules = modules or []

    @property
    def module_ids(self) -> list[str]:
        """Return the module ids targeted by this zone."""
        return [
            m.get("id")
            for m in self.modules
            if isinstance(m, dict) and m.get("id") is not None
        ]

    @property
    def dhw_states(self) -> list[str]:
        """Return the DHW states for all modules in this zone."""
        return [
            m.get("dhw_state")
            for m in self.modules
            if isinstance(m, dict) and m.get("dhw_state") is not None
        ]

    @staticmethod
    def from_dict(data: dict[str, Any], type: str) -> IntuisEventZone:  # noqa: ARG004
        """Create an event zone from a dictionary."""
        return IntuisEventZone(
            id=data["id"],
            name=data.get("name", f"Zone {data['id']}"),
            modules=data.get("modules", [])
        )


class IntuisTimetable:
    """Class to represent a timetable in the Intuis Connect system."""

    def __init__(self, zone_id: int, m_offset: int) -> None:
        """Initialize the timetable."""
        self.zone_id = zone_id
        self.m_offset = m_offset

    @staticmethod
    def from_dict(data: dict[str, Any]) -> IntuisTimetable | None:
        """Create a timetable from a dictionary.

        Returns None if the data is malformed (missing required fields).
        """
        try:
            zone_id = data["zone_id"]
            m_offset = data["m_offset"]
            return IntuisTimetable(zone_id=zone_id, m_offset=m_offset)
        except (KeyError, TypeError) as err:
            _LOGGER.warning(
                "Skipping malformed timetable entry: %s (error: %s)",
                data,
                err,
            )
            return None


class IntuisSchedule:

    def __init__(self, timetables: list[IntuisTimetable], zones: list[IntuisZone], name: str, default: bool,
                 id: str, type: str, selected: bool) -> None:
        """Initialize the Intuis schedule."""
        self.timetables = timetables
        self.zones = zones
        self.name = name
        self.default = default
        self.id = id
        self.type = type
        self.selected = selected
        _LOGGER.debug("Initialized IntuisSchedule with id: %s, name: %s", id, name)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> IntuisSchedule:
        """Create an Intuis schedule from a dictionary."""
        _LOGGER.debug("Creating IntuisSchedule from data: %s", data)
        # API returns "timetable" (singular) but we store as "timetables" internally
        timetable_data = data.get("timetable", data.get("timetables", []))
        # Filter out None entries from malformed timetable data
        timetables = [
            t for t in (IntuisTimetable.from_dict(entry) for entry in timetable_data)
            if t is not None
        ]

        type = data["type"]

        # Parse zones with error handling for malformed entries
        zones = []
        for z in data.get("zones", []):
            try:
                zones.append(IntuisZone.from_dict(z, type))
            except (KeyError, TypeError, ValueError) as err:
                _LOGGER.warning(
                    "Skipping malformed zone entry: %s (error: %s)",
                    z,
                    err,
                )

        if type is None:
            raise ValueError("Schedule type is required")
        if type not in ["therm", "electricity", "event"]:
            raise ValueError(f"Unknown schedule type: {type}")
        if type == "therm":
            return IntuisThermSchedule(
                timetables=timetables,
                zones=zones,
                name=data.get("name", f"Schedule {data['id'][-6:]}"),
                default=data.get("default", False),
                away_temp=data.get("away_temp", 12),
                hg_temp=data.get("hg_temp", 7),
                id=data["id"],
                type=type,
                selected=data.get("selected", False)
            )
        if type == "electricity":
            return IntuisElectricitySchedule(
                timetables=timetables,
                zones=zones,
                name=data.get("name", f"Electricity {data['id'][-6:]}"),
                default=data.get("default", False),
                id=data["id"],
                type=type,
                selected=data.get("selected", False),
                tariff=data.get("tariff", ""),
                tariff_option=data.get("tariff_option", ""),
                power_threshold=data.get("power_threshold", 0),
                contract_power_unit=data.get("contract_power_unit", ""),
                version=data.get("version", 1)
            )
        if type == "event":
            return IntuisEventSchedule(
                timetables=timetables,
                zones=zones,
                name=data.get("name", f"Schedule {data['id'][-6:]}"),
                default=data.get("default", False),
                id=data["id"],
                type=type,
                selected=data.get("selected", False)
            )
        raise ValueError(f"Unknown schedule type: {type}")


class IntuisThermSchedule(IntuisSchedule):
    """Class to represent a thermostat schedule in the Intuis Connect system."""

    def __init__(self, timetables: list[IntuisTimetable], zones: list[IntuisZone], name: str, default: bool,
                 away_temp: int, hg_temp: int, id: str, type: str, selected: bool) -> None:
        """Initialize the thermostat schedule."""
        IntuisSchedule.__init__(self, timetables, zones, name, default, id, type, selected)
        _LOGGER.debug("Initialized IntuisThermSchedule with id: %s, name: %s", id, name)
        self.away_temp = away_temp
        self.hg_temp = hg_temp


class IntuisElectricitySchedule(IntuisSchedule):
    """Class to represent an electricity schedule in the Intuis Connect system."""

    def __init__(self, timetables: list[IntuisTimetable], zones: list[IntuisZone], name: str, default: bool,
                 id: str, type: str, selected: bool, tariff: str, tariff_option: str, power_threshold: int,
                 contract_power_unit: str, version: int) -> None:
        """Initialize the electricity schedule."""
        IntuisSchedule.__init__(self, timetables, zones, name, default, id, type, selected)
        _LOGGER.debug("Initialized IntuisElectricitySchedule with id: %s, name: %s", id, name)
        self.tariff = tariff
        self.tariff_option = tariff_option
        self.power_threshold = power_threshold
        self.contract_power_unit = contract_power_unit
        self.version = version


class IntuisEventSchedule(IntuisSchedule):
    """Class to represent an event schedule in the Intuis Connect system."""

    def __init__(self, timetables: list[IntuisTimetable], zones: list[IntuisZone], name: str, default: bool,
                 id: str, type: str, selected: bool) -> None:
        """Initialize the event schedule."""
        IntuisSchedule.__init__(self, timetables, zones, name, default, id, type, selected)
        _LOGGER.debug("Initialized IntuisEventSchedule with id: %s, name: %s", id, name)

    def get_zone_by_id(self, zone_id: int) -> IntuisEventZone | None:
        """Return the event zone with the given id."""
        for z in self.zones:
            if isinstance(z, IntuisEventZone) and z.id == zone_id:
                return z
        return None
