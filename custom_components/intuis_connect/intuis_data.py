"""Data handling for the Intuis Connect integration."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from .intuis_api.api import IntuisAPI
from .intuis_api.mapper import extract_modules, extract_rooms
from .entity.intuis_home_config import IntuisHomeConfig
from .entity.intuis_room import IntuisRoomDefinition
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
        self._last_update_timestamp: datetime | None = None
        self._last_reset_date = datetime.now().date()

    async def async_update(self) -> dict[str, Any]:
        """Fetch and process data from the API."""
        now = datetime.now()
        is_new_day = self._last_reset_date != now.date()
        if is_new_day:
            _LOGGER.debug("New day detected, resetting minutes counter and energy cache")
            self._minutes_counter.clear()
            self._energy_cache.clear()
            self._last_reset_date = now.date()

        _LOGGER.debug("Starting data update at %s", now)

        home = await self._api.async_get_home_status()
        modules = extract_modules(home)
        data_by_room = extract_rooms(home, modules, self._minutes_counter, self._rooms_definitions, self._last_update_timestamp)

        config = IntuisHomeConfig.from_dict(await self._api.async_get_config())

        self._last_update_timestamp = now

        # return structured data
        _LOGGER.debug("Coordinator update completed")
        result = {
            "id": self._api.home_id,
            "home_id": self._api.home_id,
            "home_config": config,
            "rooms": data_by_room,
            "modules": modules,
            "schedules": self._schedules,
        }

        _LOGGER.debug("Returning data: %s", result)
        return result
