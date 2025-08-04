from __future__ import annotations

import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)


class IntuisScheduleRoom:
    """Class to represent a room in the Intuis Connect system."""

    def __init__(self, id: str, therm_setpoint_temperature) -> None:
        """Initialize the room."""
        self.id = id
        self.therm_setpoint_temperature = therm_setpoint_temperature

    @staticmethod
    def from_dict(data: dict[str, Any]) -> IntuisScheduleRoom:
        """Create a room from a dictionary."""
        return IntuisScheduleRoom(
            id=data["id"],
            therm_setpoint_temperature=data["therm_setpoint_temperature"]
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
        if type == "temp":
            return IntuisTempZone.from_dict(data, type)
        if type == "price":
            return IntuisPriceZone.from_dict(data, type)
        raise ValueError(f"Unknown zone type: {type}")


class IntuisTempZone(IntuisZone):
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
    def from_dict(data: dict[str, Any], type: str) -> IntuisTempZone:
        """Create a zone from a dictionary."""
        rooms_temp = [IntuisRoomTemperature.from_dict(rt) for rt in data.get("rooms_temp", [])]
        rooms = [IntuisScheduleRoom.from_dict(r) for r in data.get("rooms", [])]
        return IntuisTempZone(
            id=data["id"],
            name=data["name"],
            type=data["type"],
            rooms_temp=rooms_temp,
            rooms=rooms
        )


class IntuisPriceZone(IntuisZone):
    """Class to represent a price zone in the Intuis Connect system."""

    def __init__(self, id: int, price_type: str, price: float) -> None:
        """Initialize the price zone."""
        IntuisZone.__init__(self, id)
        self.price_type = price_type
        self.price = price

    @staticmethod
    def from_dict(data: dict[str, Any], type: str) -> IntuisPriceZone:
        """Create a price zone from a dictionary."""
        return IntuisPriceZone(
            id=data["id"],
            price_type=data["price_type"],
            price=data["price"]
        )


class IntuisTimetable:
    """Class to represent a timetable in the Intuis Connect system."""

    def __init__(self, zone_id: int, m_offset: int) -> None:
        """Initialize the timetable."""
        self.zone_id = zone_id
        self.m_offset = m_offset

    @staticmethod
    def from_dict(data: dict[str, Any]) -> IntuisTimetable:
        """Create a timetable from a dictionary."""
        return IntuisTimetable(
            zone_id=data["zone_id"],
            m_offset=data["m_offset"]
        )


class IntuisSchedule:

    def __init__(self, timetables: list[IntuisTimetable], zones: list[IntuisZone], name: str, default: bool,
                 away_temp: int, hg_temp: int, id: str, type: str, selected: bool) -> None:
        """Initialize the Intuis schedule."""
        self.timetables = timetables
        self.zones = zones
        self.name = name
        self.default = default
        self.away_temp = away_temp
        self.hg_temp = hg_temp
        self.id = id
        self.type = type
        self.selected = selected
        _LOGGER.debug("Initialized IntuisSchedule with id: %s, name: %s", id, name)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> IntuisSchedule:
        """Create an Intuis schedule from a dictionary."""
        _LOGGER.debug("Creating IntuisSchedule from data: %s", data)
        timetables = [IntuisTimetable.from_dict(t) for t in data.get("timetables", [])]

        type = data["type"],

        zones = [IntuisZone.from_dict(z, type) for z in data.get("zones", [])]

        return IntuisSchedule(
            timetables=timetables,
            zones=zones,
            name=data["name"],
            default=data["default"],
            away_temp=data["away_temp"],
            hg_temp=data["hg_temp"],
            id=data["id"],
            type=data["type"],
            selected=data.get("selected", False)
        )
