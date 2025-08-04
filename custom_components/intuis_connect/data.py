"""Data handling for the Intuis Connect integration."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, List

from .api import IntuisAPI
from .intuis_module import IntuisModule
from .intuis_schedule import IntuisSchedule

_LOGGER = logging.getLogger(__name__)


class IntuisRoomDefinition:
    """Class to define a room in the Intuis Connect system."""

    def __init__(self, id: str, name: str, type: str, module_ids: list[str] = None,
                 modules: list[dict[str, Any]] = None, therm_relay: dict[str, Any] = None) -> None:
        """Initialize the room definition."""
        self.id = id
        self.name = name
        self.type = type
        self.module_ids = module_ids or []
        self.modules = modules or []
        self.therm_relay = therm_relay

    def __repr__(self) -> str:
        """Return a string representation of the room."""
        return f"IntuisRoomDefinition(id={self.id}, name={self.name}, type={self.type}, module_ids={self.module_ids}, modules={self.modules}, therm_relay={self.therm_relay})"

    @staticmethod
    def from_dict(data: dict[str, Any]) -> IntuisRoomDefinition:
        """Create a room definition from a dictionary."""
        return IntuisRoomDefinition(
            id=data["id"],
            name=data["name"],
            type=data["type"],
            module_ids=data.get("module_ids", []),
            modules=data.get("modules", []),
            therm_relay=data.get("therm_relay")
        )


class IntuisRoom:
    """Class to represent a room in the Intuis Connect system."""

    heating: bool = False
    minutes: int = 0
    energy: float = 0.0

    def __init__(self, definition: IntuisRoomDefinition, id: str, name: str, mode: str, target_temperature: float,
                 temperature: float, presence: bool, open_window: bool, anticipation: bool,
                 muller_type: str, boost_status: str, modules: List[IntuisModule]) -> None:
        """Initialize the room with its definition."""
        self.definition = definition
        self.id = id
        self.name = name
        self.mode = mode
        self.target_temperature = target_temperature
        self.temperature = temperature
        self.presence = presence
        self.open_window = open_window
        self.anticipation = anticipation
        self.muller_type = muller_type
        self.boost_status = boost_status
        self.modules = modules

    @staticmethod
    def from_dict(definition: IntuisRoomDefinition, data: dict[str, Any], modules: List[IntuisModule]) -> IntuisRoom:
        """Create a room from a dictionary and its definition."""

        # Filter modules based on the room definition
        filtered_modules = [module for module in modules if module.id in definition.module_ids]

        return IntuisRoom(
            definition=definition,
            id=data["id"],
            name=definition.name,
            mode=data.get("therm_setpoint_mode", "unknown"),
            temperature=data.get("therm_measured_temperature", 0.0),
            target_temperature=data.get("therm_setpoint_temperature", 0.0),
            presence=data.get("presence", False),
            open_window=data.get("open_window", False),
            anticipation=data.get("anticipation", False),
            muller_type=data.get("muller_type", ""),
            boost_status=data.get("boost_status", "disabled"),
            modules=filtered_modules
        )

    def __repr__(self) -> str:
        """Return a string representation of the room."""
        return f"IntuisRoom(definition={self.definition}, id={self.id}, name={self.name}, mode={self.mode}, target_temperature={self.target_temperature}, temperature={self.temperature}, heating={self.heating}, presence={self.presence}, open_window={self.open_window}, anticipation={self.anticipation}, muller_type={self.muller_type}, boost_status={self.boost_status}, modules={self.modules})"

class IntuisData:
    """Class to handle data fetching and processing for the Intuis Connect integration."""

    def __init__(self, api: IntuisAPI, rooms_definitions: dict[str, IntuisRoomDefinition]) -> None:
        """Initialize the data handler."""
        self._api = api
        self._energy_cache: dict[str, float] = {}
        self._minutes_counter: dict[str, int] = {}
        self._rooms_definitions = rooms_definitions

    async def async_update(self) -> dict[str, Any]:
        """Fetch and process data from the API."""
        now = datetime.now()
        today_iso = now.strftime("%Y-%m-%d")

        # --- fetch raw data ---
        home = await self._api.async_get_home_status()
        rooms_raw: list[dict[str, Any]] = home.get("rooms", [])
        modules_raw: list[dict[str, Any]] = home.get("modules", [])

        # --- process modules ---
        modules: List[IntuisModule] = []
        for module in modules_raw:
            mid = module["id"]
            modules.append(IntuisModule.from_dict(module))
            _LOGGER.debug("Module %s data: %s", mid, module)

        # --- process rooms ---
        data_by_room: dict[str, IntuisRoom] = {}
        for room in rooms_raw:
            rid = room["id"]
            info: IntuisRoom = IntuisRoom.from_dict(
                self._rooms_definitions.get(rid),
                room,
                modules
            )

            # ---- heating-minutes counter ---
            if rid not in self._minutes_counter:
                self._minutes_counter[rid] = 0

            if info.heating:
                self._minutes_counter[rid] += 5  # Assuming update interval is 5 minutes
            if now.hour == 0 and now.minute < 5:  # Reset daily
                self._minutes_counter[rid] = 0
            info.minutes = self._minutes_counter[rid]

            # ---- daily kWh ---
            # cache_key = f"{rid}_{today_iso}"
            # if cache_key not in self._energy_cache and now.hour >= 2:
            #     _LOGGER.debug("Fetching energy data for room %s on %s", rid, today_iso)
            #     self._energy_cache[cache_key] = await self._api.async_get_home_measure(
            #         rid, today_iso
            #     )
            # info.energy = self._energy_cache.get(cache_key, 0.0)
            _LOGGER.debug("Room %s data compiled: %s", rid, info)

            data_by_room[rid] = info

        # --- pull the active schedule ---
        schedules = [IntuisSchedule.from_dict(t) for t in home.get("schedules", [])]

        # return structured data
        _LOGGER.debug("Coordinator update completed")
        result = {
            "id": self._api.home_id,
            "home_id": self._api.home_id,
            "rooms": data_by_room,
            "modules": modules,
            "schedules": schedules
        }

        _LOGGER.debug("Returning data: %s", result)
        return result
