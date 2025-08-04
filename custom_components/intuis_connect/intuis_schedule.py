from __future__ import annotations

from typing import Any


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


class IntuisZone:
    """Class to represent a zone in the Intuis Connect system."""

    def __init__(self, id: int, name: str, type: int,
                 rooms_temp: list[IntuisRoomTemperature],
                 rooms: list[IntuisScheduleRoom]) -> None:
        """Initialize the zone."""
        self.id = id
        self.name = name
        self.type = type
        self.rooms_temp = rooms_temp
        self.rooms = rooms

    @staticmethod
    def from_dict(data: dict[str, Any]) -> IntuisZone:
        """Create a zone from a dictionary."""
        rooms_temp = [IntuisRoomTemperature.from_dict(rt) for rt in
                      data.get("rooms_temp", [])]
        rooms = [IntuisScheduleRoom.from_dict(r) for r in data.get("rooms", [])]
        return IntuisZone(
            id=data["id"],
            name=data["name"],
            type=data["type"],
            rooms_temp=rooms_temp,
            rooms=rooms
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


class IntuisSchedule:

    def __init__(self, timetables: list[IntuisTimetable],
                 zones: list[IntuisZone]) -> None:
        """Initialize the Intuis schedule."""
        self.timetables = timetables
        self.zones = zones

    @staticmethod
    def from_dict(data: dict[str, Any]) -> IntuisSchedule:
        """Create an Intuis schedule from a dictionary."""
        timetables = [IntuisTimetable.from_dict(t) for t in data.get("timetables", [])]
        zones = [IntuisZone.from_dict(z) for z in data.get("zones", [])]
        return IntuisSchedule(timetables=timetables, zones=zones)
