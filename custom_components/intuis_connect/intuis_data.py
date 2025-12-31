"""Data handling for the Intuis Connect integration."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
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
    CONF_INDEFINITE_MODE,
    CONF_MANUAL_DURATION,
    CONF_AWAY_DURATION,
    CONF_BOOST_DURATION,
    DEFAULT_INDEFINITE_MODE,
)

# Re-apply override this many seconds before it expires (when indefinite mode is on)
INDEFINITE_REAPPLY_BUFFER = 300  # 5 minutes

_LOGGER = logging.getLogger(__name__)


class IntuisData:
    """Class to handle data fetching and processing for the Intuis Connect integration."""

    def __init__(
        self,
        api: IntuisAPI,
        intuis_home: IntuisHome,
        overrides: dict[str, dict] | None = None,
        get_options: callable = None,
    ) -> None:
        """Initialize the data handler."""
        self._api = api
        self._energy_cache: dict[str, float] = {}
        self._minutes_counter: dict[str, int] = {}
        self._intuis_home = intuis_home
        self._last_update_timestamp: datetime | None = None
        self._last_reset_date = datetime.now().date()
        # sticky overrides: { room_id: { mode, temp, end, sticky } }
        self._overrides: dict[str, dict] = overrides or {}
        # Callback to get current options from config entry
        self._get_options = get_options or (lambda: {})

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

        # Get current options
        options = self._get_options()
        indefinite_mode = options.get(CONF_INDEFINITE_MODE, DEFAULT_INDEFINITE_MODE)

        # Apply sticky overrides if backend reverted at or after end time
        # OR if indefinite mode is enabled and we're approaching expiry
        now_ts = int(time.time())
        for room_id, room in data_by_room.items():
            override = self._overrides.get(room_id)
            if not override or not override.get("sticky", True):
                continue
            try:
                end_ts = int(override.get("end", 0))
            except (TypeError, ValueError):
                end_ts = 0

            desired_mode: str = override.get("mode")
            desired_temp = override.get("temp")

            # Get configured duration for this mode
            duration_min = options.get(CONF_MANUAL_DURATION, DEFAULT_MANUAL_DURATION)
            if desired_mode == API_MODE_AWAY:
                duration_min = options.get(CONF_AWAY_DURATION, DEFAULT_AWAY_DURATION)
            elif desired_mode == API_MODE_BOOST:
                duration_min = options.get(CONF_BOOST_DURATION, DEFAULT_BOOST_DURATION)

            # Check if we should re-apply the override
            should_reapply = False
            reason = ""

            if indefinite_mode and end_ts:
                # In indefinite mode: re-apply before expiry (5 min buffer)
                if now_ts >= end_ts - INDEFINITE_REAPPLY_BUFFER:
                    should_reapply = True
                    reason = "indefinite mode - approaching expiry"
            elif end_ts and now_ts >= end_ts - 2:
                # Normal mode: check if backend reverted after expiry
                mismatch = False
                if desired_mode and room.mode != desired_mode:
                    mismatch = True
                if desired_temp is not None:
                    try:
                        mismatch = mismatch or abs(float(room.target_temperature) - float(desired_temp)) > 0.1
                    except Exception:
                        mismatch = True
                if mismatch:
                    should_reapply = True
                    reason = "backend reverted after expiry"

            if should_reapply:
                _LOGGER.info(
                    "Re-applying override for room %s (%s): mode=%s temp=%s duration=%d min",
                    room_id,
                    reason,
                    desired_mode,
                    desired_temp,
                    duration_min,
                )
                await self._api.async_set_room_state(
                    room_id,
                    desired_mode,
                    float(desired_temp) if desired_temp is not None else None,
                    duration_min,
                )
                # Extend local end timestamp
                self._overrides[room_id]["end"] = int(time.time()) + duration_min * 60

        config = IntuisHomeConfig.from_dict(await self._api.async_get_config())

        # Fetch energy data (daily kWh per room)
        await self._fetch_energy_data(data_by_room, now)

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

    async def _fetch_energy_data(
        self, data_by_room: dict[str, Any], now: datetime
    ) -> None:
        """Fetch energy consumption data for all rooms."""
        # Only fetch after 2 AM to ensure previous day's data is available
        if now.hour < 2:
            _LOGGER.debug("Skipping energy fetch before 2 AM")
            return

        today_iso = now.date().isoformat()

        # Check if we already have cached data for today
        if self._energy_cache.get("_date") == today_iso:
            # Use cached data
            for room_id, room in data_by_room.items():
                room.energy = self._energy_cache.get(room_id, 0.0)
            return

        # Build list of rooms with bridge_ids for the API call
        rooms_for_api: list[dict[str, str]] = []
        for room_id, room in data_by_room.items():
            if room.bridge_id:
                rooms_for_api.append({"id": room_id, "bridge": room.bridge_id})
            else:
                _LOGGER.debug("Room %s has no bridge_id, skipping energy fetch", room_id)

        if not rooms_for_api:
            _LOGGER.debug("No rooms with bridge_id found, skipping energy fetch")
            return

        # Calculate epoch timestamps for today (midnight to midnight)
        today_start = datetime.combine(now.date(), datetime.min.time(), tzinfo=timezone.utc)
        today_end = datetime.combine(now.date(), datetime.max.time(), tzinfo=timezone.utc)
        date_begin = int(today_start.timestamp())
        date_end = int(today_end.timestamp())

        _LOGGER.debug("Fetching energy data for %d rooms", len(rooms_for_api))

        energy_data = await self._api.async_get_energy_measures(
            rooms_for_api, date_begin, date_end
        )

        # Cache the results and populate room.energy
        self._energy_cache.clear()
        self._energy_cache["_date"] = today_iso
        for room_id, room in data_by_room.items():
            kwh = energy_data.get(room_id, 0.0)
            self._energy_cache[room_id] = kwh
            room.energy = kwh

        _LOGGER.debug("Energy data cached for %s: %s", today_iso, energy_data)
