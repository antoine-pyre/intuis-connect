"""Data handling for the Intuis Connect integration."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
import time

from .entity.intuis_home import IntuisHome
from .entity.intuis_home_config import IntuisHomeConfig
from .intuis_api.api import IntuisAPI
from .intuis_api.mapper import extract_modules, extract_rooms
from .utils.const import (
    API_MODE_MANUAL,
    API_MODE_AWAY,
    API_MODE_BOOST,
    DEFAULT_MANUAL_DURATION,
    DEFAULT_AWAY_DURATION,
    DEFAULT_BOOST_DURATION,
)

_LOGGER = logging.getLogger(__name__)


class IntuisData:
    """Class to handle data fetching and processing for the Intuis Connect integration."""

    def __init__(self, api: IntuisAPI, intuis_home: IntuisHome, overrides: dict[str, dict] | None = None,
                 hass=None, entry_id: str | None = None) -> None:
        """Initialize the data handler."""
        self._api = api
        self._energy_cache: dict[str, float] = {}
        self._minutes_counter: dict[str, int] = {}
        self._intuis_home = intuis_home
        self._last_update_timestamp: datetime | None = None
        self._last_reset_date = datetime.now().date()
        # sticky overrides: { room_id: { mode, temp, end, sticky } }
        self._overrides: dict[str, dict] = overrides or {}
        # optionally persist overrides back to config entry if provided
        self._hass = hass
        self._entry_id = entry_id

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
        data_by_room = extract_rooms(home, modules, self._minutes_counter, self._intuis_home.rooms,
                                     self._last_update_timestamp)

        # Apply sticky overrides if backend reverted at or after end time
        now_ts = int(time.time())
        for room_id, room in data_by_room.items():
            override = self._overrides.get(room_id)
            if not override or not override.get("sticky", True):
                continue
            try:
                end_ts = int(override.get("end", 0))
            except (TypeError, ValueError):
                end_ts = 0
            if end_ts and now_ts >= end_ts - 2:  # small slack
                desired_mode: str = override.get("mode")
                desired_temp = override.get("temp")
                # Check if backend reverted (mode/temp mismatch)
                mismatch = False
                if desired_mode and room.mode != desired_mode:
                    mismatch = True
                if desired_temp is not None:
                    try:
                        mismatch = mismatch or abs(float(room.target_temperature) - float(desired_temp)) > 0.1
                    except Exception:  # safety
                        mismatch = True
                if mismatch:
                    duration_min = DEFAULT_MANUAL_DURATION
                    if desired_mode == API_MODE_AWAY:
                        duration_min = DEFAULT_AWAY_DURATION
                    elif desired_mode == API_MODE_BOOST:
                        duration_min = DEFAULT_BOOST_DURATION
                    # Re-apply intended override
                    _LOGGER.info(
                        "Re-applying sticky override for room %s: mode=%s temp=%s",
                        room_id,
                        desired_mode,
                        desired_temp,
                    )
                    await self._api.async_set_room_state(
                        room_id,
                        desired_mode,
                        float(desired_temp) if desired_temp is not None else None,
                        duration_min,
                    )
                    # Extend local end timestamp
                    new_end = int(time.time()) + duration_min * 60
                    self._overrides[room_id]["end"] = new_end
                    # Persist the updated overrides back to the config entry options if possible
                    try:
                        if self._hass and self._entry_id:
                            entry = self._hass.config_entries.async_get_entry(self._entry_id)
                            if entry is not None:
                                new_options = dict(entry.options) if entry.options is not None else {}
                                new_options["overrides"] = self._overrides
                                self._hass.config_entries.async_update_entry(entry, options=new_options)
                    except Exception:  # best-effort persistence
                        _LOGGER.debug("Failed to persist overrides after re-applying for entry %s", self._entry_id, exc_info=True)

        config = IntuisHomeConfig.from_dict(await self._api.async_get_config())

        self._last_update_timestamp = now

        # return structured data
        _LOGGER.debug("Coordinator update completed")
        result = {
            "id": self._intuis_home.id,
            "home_id": self._intuis_home.id,
            "home_config": config,
            "rooms": data_by_room,
            "modules": modules,
            "intuis_home": self._intuis_home,
            "schedules": self._intuis_home.schedules,
        }

        _LOGGER.debug("Returning data: %s", result)
        return result
