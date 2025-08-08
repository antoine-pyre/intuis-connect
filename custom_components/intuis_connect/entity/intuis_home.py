"""
intuis_home.py – Data model for Intuis “home” objects returned by /getHomeData
Author: Your Name • Licence: MIT
"""

from __future__ import annotations

from typing import List, Optional, Tuple, Dict, Any

from pydantic import Field

from custom_components.intuis_connect.entity.intuis_room import IntuisRoomDefinition
from custom_components.intuis_connect.entity.intuis_schedule import IntuisSchedule


class Capability:
    """Represents an item in the `capabilities` list."""
    name: str
    available: bool


class IntuisHome:
    """
    Home-level configuration returned by Intuis Cloud.

    Use `IntuisHome.from_api(body["homes"][0])` to create an instance.
    """

    id: str = Field(alias="id")
    name: str
    altitude: Optional[float] = None
    coordinates: Tuple[float, float]
    country: str
    timezone: str
    city: Optional[str] = None
    currency_code: Optional[str] = None

    nb_users: Optional[int] = None
    capabilities: List[Capability] = Field(default_factory=list)
    temperature_control_mode: Optional[str] = None
    therm_mode: Optional[str] = None
    therm_setpoint_default_duration: Optional[int] = None
    therm_heating_priority: Optional[str] = None
    anticipation: Optional[bool] = None

    def __init__(self, id: str, name: str, coordinates: Tuple[float, float], country: str, timezone: str,
                 altitude: Optional[float] = None, city: Optional[str] = None, currency_code: Optional[str] = None,
                 nb_users: Optional[int] = None, capabilities: Optional[List[Capability]] = None,
                 temperature_control_mode: Optional[str] = None, therm_mode: Optional[str] = None,
                 therm_setpoint_default_duration: Optional[int] = None, therm_heating_priority: Optional[str] = None,
                 anticipation: Optional[bool] = None, rooms: Dict[str, IntuisRoomDefinition] = None,
                 contract_power_unit: str = None,
                 place_improved: bool = None,
                 trust_location: bool = None,
                 therm_absence_location: bool = None,
                 therm_absense_autoway: bool = None,
                 schedules: List[IntuisSchedule] = None):
        """Initialize the IntuisHome object.
        :param contract_power_unit:
        :param place_improved:
        :param trust_location:
        :param therm_absence_location:
        :param therm_absense_autoway:
        :param schedules:
        """
        self.id = id
        self.name = name
        self.coordinates = coordinates
        self.country = country
        self.timezone = timezone
        self.altitude = altitude
        self.city = city
        self.currency_code = currency_code
        self.nb_users = nb_users
        self.capabilities = capabilities or []
        self.temperature_control_mode = temperature_control_mode
        self.therm_mode = therm_mode
        self.therm_setpoint_default_duration = therm_setpoint_default_duration
        self.therm_heating_priority = therm_heating_priority
        self.anticipation = anticipation
        self.rooms: dict[str, IntuisRoomDefinition] = rooms
        self.contract_power_unit = contract_power_unit
        self.place_improved = place_improved
        self.trust_location = trust_location
        self.therm_absence_location = therm_absence_location
        self.therm_absense_autoway = therm_absense_autoway
        self.schedules: List[IntuisSchedule] = schedules

    # ---------- helpers -----------------------------------------------------

    @property
    def lon(self) -> float:  # convenience split of coordinates
        return self.coordinates[0]

    @property
    def lat(self) -> float:
        return self.coordinates[1]

    @classmethod
    def from_api(cls, raw_home: Dict[str, Any]) -> IntuisHome:
        """Create an IntuisHome from a `/getHomeData` API response."""
        rooms_definitions: dict[str, IntuisRoomDefinition] = {
            r["id"]: IntuisRoomDefinition.from_dict(r)
            for r in raw_home["rooms"]
        }

        schedules = [IntuisSchedule.from_dict(t) for t in raw_home.get("schedules", [])]

        raw_coordinates: List | None = raw_home.get("coordinates", None)
        coordinates: tuple[float, float] | None
        if isinstance(raw_coordinates, list) and len(raw_coordinates) == 2:
            # Ensure coordinates are a tuple of (longitude, latitude)
            coordinates = (float(raw_coordinates[0]), float(raw_coordinates[1]))
        else:
            coordinates = None

        return cls(
            id=raw_home["id"],
            name=raw_home["name"],
            altitude=raw_home.get("altitude"),
            coordinates=coordinates,
            country=raw_home["country"],
            timezone=raw_home["timezone"],
            city=raw_home.get("city"),
            currency_code=raw_home.get("currency_code"),
            contract_power_unit=raw_home.get("contract_power_unit"),
            place_improved=raw_home.get("place_improved"),
            trust_location=raw_home.get("trust_location"),
            therm_absence_location=raw_home.get("therm_absence_location"),
            therm_absense_autoway=raw_home.get("therm_absense_autoway"),
            rooms=list(rooms_definitions.values()),
            schedules=schedules
        )
