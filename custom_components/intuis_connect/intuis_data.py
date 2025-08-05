"""Data handling for the Intuis Connect integration."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, List

from .api import IntuisAPI
from .entity.intuis_module import IntuisModule
from .entity.intuis_room import IntuisRoomDefinition, IntuisRoom
from .entity.intuis_schedule import IntuisSchedule

_LOGGER = logging.getLogger(__name__)


class IntuisData:
    """Class to handle data fetching and processing for the Intuis Connect integration."""

    def __init__(self, api: IntuisAPI, rooms_definitions: dict[str, IntuisRoomDefinition],
                 schedules: list[IntuisSchedule]) -> None:
        """Initialize the data handler."""
        self._api = api
        self._energy_cache: dict[str, float] = {}
        self._minutes_counter: dict[str, int] = {}
        self._rooms_definitions = rooms_definitions
        self._schedules = schedules

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

        # return structured data
        _LOGGER.debug("Coordinator update completed")
        result = {
            "id": self._api.home_id,
            "home_id": self._api.home_id,
            "rooms": data_by_room,
            "modules": modules,
            "schedules": self._schedules,
        }

        _LOGGER.debug("Returning data: %s", result)
        return result
