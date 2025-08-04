"""Data handling for the Intuis Connect integration."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from .api import IntuisAPI

_LOGGER = logging.getLogger(__name__)


class IntuisData:
    """Class to handle data fetching and processing for the Intuis Connect integration."""

    def __init__(self, api: IntuisAPI) -> None:
        """Initialize the data handler."""
        self._api = api
        self._energy_cache: dict[str, float] = {}
        self._minutes_counter: dict[str, int] = {}

    async def async_update(self) -> dict[str, Any]:
        """Fetch and process data from the API."""
        now = datetime.now()
        today_iso = now.strftime("%Y-%m-%d")

        # --- fetch raw data ---
        home = await self._api.async_get_home_status()
        rooms_raw: list[dict[str, Any]] = home.get("rooms", [])
        modules_raw: list[dict[str, Any]] = home.get("modules", [])

        # --- process modules ---
        modules: dict[str, dict[str, Any]] = {
            m["id"]: {
                "id": m["id"],
                "name": m["name"],
                "room_id": m.get("room_id"),
                "locked": m.get("keypad_locked", 0) == 1,
            }
            for m in modules_raw
        }

        # --- process rooms ---
        data_by_room: dict[str, dict[str, Any]] = {}
        for room in rooms_raw:
            rid = room["id"]
            info: dict[str, Any] = {
                "id": rid,
                "name": room["name"],
                "mode": room.get("therm_setpoint_mode"),
                "target_temperature": room.get("therm_setpoint_temperature"),
                "temperature": room.get("therm_measured_temperature"),
                "heating": room.get("heating_status", 0) == 1,
                "presence": any(
                    m.get("presence_detected")
                    for m in modules_raw
                    if m.get("room_id") == rid
                ),
                "open_window": any(
                    m.get("open_window_detected")
                    for m in modules_raw
                    if m.get("room_id") == rid
                ),
                "anticipation": any(
                    m.get("anticipating") for m in modules_raw if m.get("room_id") == rid
                ),
                "power": max(
                    (
                        m.get("heating_power_request", 0)
                        for m in modules_raw
                        if m.get("room_id") == rid
                    ),
                    default=0,
                ),
            }

            # ---- heating-minutes counter ---
            if rid not in self._minutes_counter:
                self._minutes_counter[rid] = 0

            if info["heating"]:
                self._minutes_counter[rid] += 5  # Assuming update interval is 5 minutes
            if now.hour == 0 and now.minute < 5:  # Reset daily
                self._minutes_counter[rid] = 0
            info["minutes"] = self._minutes_counter[rid]

            # ---- daily kWh ---
            cache_key = f"{rid}_{today_iso}"
            if cache_key not in self._energy_cache and now.hour >= 2:
                _LOGGER.debug("Fetching energy data for room %s on %s", rid, today_iso)
                self._energy_cache[cache_key] = await self._api.async_get_home_measure(
                    rid, today_iso
                )
            info["energy"] = self._energy_cache.get(cache_key, 0.0)
            _LOGGER.debug("Room %s data compiled: %s", rid, info)

            data_by_room[rid] = info

        # --- pull the active schedule ---
        schedule: dict[str, Any] = {}
        active_id = home.get("active_schedule_id")
        if active_id:
            # This method might need to be implemented in api.py if not present
            if hasattr(self._api, "async_get_schedule"):
                schedule = await self._api.async_get_schedule(
                    self._api.home_id, active_id
                )
                _LOGGER.debug(
                    "Active schedule for home %s: %s", self._api.home_id, schedule
                )
            else:
                _LOGGER.warning("async_get_schedule not found in API")

        # return structured data
        _LOGGER.debug("Coordinator update completed")
        result =  {
            "id": self._api.home_id,
            "home_id": self._api.home_id,
            "active_schedule_id": active_id,
            "rooms": data_by_room,
            "modules": modules,
            "schedule": schedule,
        }

        _LOGGER.debug("Returning data: %s", result)
        return result
