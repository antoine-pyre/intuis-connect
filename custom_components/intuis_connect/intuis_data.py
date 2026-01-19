"""Data handling for the Intuis Connect integration."""
from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from .entity.intuis_home import IntuisHome
from .entity.intuis_home_config import IntuisHomeConfig
from .intuis_api.api import IntuisAPI, APIError, CannotConnect, RateLimitError
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
    CONF_ENERGY_SCALE,
    CONF_ENERGY_RESET_HOUR,
    DEFAULT_INDEFINITE_MODE,
    DEFAULT_ENERGY_SCALE,
    DEFAULT_ENERGY_RESET_HOUR,
)

# Re-apply override this many seconds before it expires (when indefinite mode is on)
INDEFINITE_REAPPLY_BUFFER = 300  # 5 minutes

# Minimum time between re-applications to avoid API spam
MIN_REAPPLY_INTERVAL = 120  # 2 minutes

_LOGGER = logging.getLogger(__name__)


class IntuisData:
    """Class to handle data fetching and processing for the Intuis Connect integration."""

    def __init__(
        self,
        api: IntuisAPI,
        intuis_home: IntuisHome,
        overrides: dict[str, dict] | None = None,
        get_options: Callable[[], dict[str, Any]] | None = None,
        save_overrides_callback: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        """Initialize the data handler."""
        self._api = api
        self._energy_cache: dict[str, float] = {}
        self._minutes_counter: dict[str, int] = {}
        self._intuis_home = intuis_home
        self._last_update_timestamp: datetime | None = None
        # Track the last "logical day" we processed (based on reset hour, not midnight)
        self._last_logical_day: str | None = None
        # sticky overrides: { room_id: { mode, temp, end, sticky, last_reapply } }
        self._overrides: dict[str, dict] = overrides or {}
        # Callback to get current options from config entry
        self._get_options = get_options or (lambda: {})
        # Callback to persist overrides to storage
        self._save_overrides = save_overrides_callback
        # Callback to invoke on successful update (for rate limit recovery)
        self._success_callback: Callable[[], Awaitable[None]] | None = None

    def set_success_callback(
        self, callback: Callable[[], Awaitable[None]]
    ) -> None:
        """Set callback to invoke on successful data update.

        Used by the coordinator to recover polling interval after rate limiting.
        """
        self._success_callback = callback

    def _get_logical_day(self, now: datetime, reset_hour: int) -> str:
        """Get the logical day identifier based on reset hour.

        The logical day starts at reset_hour and ends at reset_hour the next calendar day.
        For example, with reset_hour=2:
        - 2024-01-15 01:30 is still logical day "2024-01-14"
        - 2024-01-15 02:00 is logical day "2024-01-15"
        """
        if now.hour < reset_hour:
            # Before reset hour: still the previous logical day
            logical_date = (now - timedelta(days=1)).date()
        else:
            # After reset hour: current logical day
            logical_date = now.date()
        return logical_date.isoformat()

    async def async_update(self) -> dict[str, Any]:
        """Fetch and process data from the API."""
        now = datetime.now()

        # Get configured reset hour
        options = self._get_options()
        reset_hour = options.get(CONF_ENERGY_RESET_HOUR, DEFAULT_ENERGY_RESET_HOUR)

        # Check if we've crossed the reset hour boundary
        current_logical_day = self._get_logical_day(now, reset_hour)
        is_new_logical_day = (
            self._last_logical_day is not None and
            self._last_logical_day != current_logical_day
        )

        if is_new_logical_day:
            _LOGGER.info(
                "New logical day detected (reset hour: %02d:00), resetting counters. "
                "Previous: %s, Current: %s",
                reset_hour,
                self._last_logical_day,
                current_logical_day,
            )
            self._minutes_counter.clear()
            self._energy_cache.clear()

        self._last_logical_day = current_logical_day

        _LOGGER.debug("Starting data update at %s (logical day: %s)", now, current_logical_day)

        try:
            home = await self._api.async_get_home_status()
        except (APIError, CannotConnect, RateLimitError) as err:
            _LOGGER.error("Failed to fetch home status from API: %s", err)
            raise

        try:
            modules = extract_modules(home)
            data_by_room = extract_rooms(home, modules, self._minutes_counter, self._intuis_home.rooms,
                                         self._last_update_timestamp)
        except (KeyError, TypeError, ValueError) as err:
            _LOGGER.error("Failed to parse home data: %s", err)
            raise

        # Get current options
        options = self._get_options()
        indefinite_mode = options.get(CONF_INDEFINITE_MODE, DEFAULT_INDEFINITE_MODE)

        # Process sticky overrides
        now_ts = int(time.time())
        overrides_changed = False
        rooms_to_clear = []

        # First, clean up orphaned overrides (rooms that no longer exist in API)
        for room_id in list(self._overrides.keys()):
            if room_id not in data_by_room:
                _LOGGER.warning(
                    "Removing orphaned override for room %s (room no longer in API response)",
                    room_id,
                )
                rooms_to_clear.append(room_id)
                overrides_changed = True

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
            last_reapply = override.get("last_reapply", 0)

            # Get configured duration for this mode
            duration_min = options.get(CONF_MANUAL_DURATION, DEFAULT_MANUAL_DURATION)
            if desired_mode == API_MODE_AWAY:
                duration_min = options.get(CONF_AWAY_DURATION, DEFAULT_AWAY_DURATION)
            elif desired_mode == API_MODE_BOOST:
                duration_min = options.get(CONF_BOOST_DURATION, DEFAULT_BOOST_DURATION)

            # Determine action based on mode
            if indefinite_mode:
                # INDEFINITE MODE: Re-apply before expiry to keep override active forever
                # Only re-apply if:
                # 1. We're within the buffer window before expiry
                # 2. Enough time has passed since last re-apply (avoid API spam)
                time_until_expiry = end_ts - now_ts
                time_since_last_reapply = now_ts - last_reapply

                if time_until_expiry <= INDEFINITE_REAPPLY_BUFFER and time_since_last_reapply >= MIN_REAPPLY_INTERVAL:
                    try:
                        _LOGGER.info(
                            "Re-applying override for room %s (indefinite mode, %ds until expiry): "
                            "mode=%s temp=%s duration=%d min",
                            room_id,
                            time_until_expiry,
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
                        # Update timestamps
                        self._overrides[room_id]["end"] = now_ts + duration_min * 60
                        self._overrides[room_id]["last_reapply"] = now_ts
                        overrides_changed = True
                    except (APIError, CannotConnect, RateLimitError) as err:
                        _LOGGER.error(
                            "Failed to re-apply override for room %s: %s",
                            room_id,
                            err,
                        )
                        # Don't update timestamps on failure, will retry next cycle
            else:
                # NON-INDEFINITE MODE: Override should expire naturally
                # Once expired, remove from overrides dict
                if now_ts > end_ts:
                    _LOGGER.debug(
                        "Override for room %s expired (end_ts=%d, now=%d), clearing",
                        room_id,
                        end_ts,
                        now_ts,
                    )
                    rooms_to_clear.append(room_id)
                    overrides_changed = True

        # Clear expired overrides (outside loop to avoid dict modification during iteration)
        for room_id in rooms_to_clear:
            self._overrides.pop(room_id, None)

        # Persist overrides if changed
        if overrides_changed and self._save_overrides:
            await self._save_overrides()

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

        # Invoke success callback for rate limit recovery
        if self._success_callback:
            try:
                await self._success_callback()
            except (TypeError, ValueError, RuntimeError) as err:
                _LOGGER.debug("Success callback error (non-fatal): %s", err)

        return result

    async def _fetch_energy_data(
        self, data_by_room: dict[str, Any], now: datetime
    ) -> None:
        """Fetch energy consumption data for all rooms."""
        # Get energy scale and reset hour from options
        options = self._get_options()
        scale = options.get(CONF_ENERGY_SCALE, DEFAULT_ENERGY_SCALE)
        reset_hour = options.get(CONF_ENERGY_RESET_HOUR, DEFAULT_ENERGY_RESET_HOUR)
        is_realtime = scale != "1day"

        # Calculate timestamps using the home's timezone
        # This ensures day boundaries align with the user's local time
        try:
            home_tz = ZoneInfo(self._api.home_timezone)
        except (KeyError, ValueError):
            _LOGGER.warning(
                "Invalid home timezone '%s', falling back to UTC",
                self._api.home_timezone,
            )
            home_tz = timezone.utc

        now_local = datetime.now(home_tz)
        today_iso = now_local.date().isoformat()

        # For daily scale, only fetch after reset hour to ensure data is available
        if not is_realtime and now_local.hour < reset_hour:
            _LOGGER.debug(
                "Skipping energy fetch before reset hour %02d:00 (daily mode)",
                reset_hour,
            )
            return

        # For daily scale, use caching. For real-time scales, always fetch fresh data.
        if not is_realtime and self._energy_cache.get("_date") == today_iso:
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

        today_start = datetime.combine(now_local.date(), datetime.min.time(), tzinfo=home_tz)
        today_end = datetime.combine(now_local.date(), datetime.max.time(), tzinfo=home_tz)

        if is_realtime:
            date_end = int(now_local.timestamp())
            end_display = now_local.isoformat()
        else:
            date_end = int(today_end.timestamp())
            end_display = today_end.isoformat()
        date_begin = int(today_start.timestamp())

        _LOGGER.debug(
            "Fetching energy data for %d rooms (scale=%s, tz=%s, range=%s to %s)",
            len(rooms_for_api),
            scale,
            home_tz,
            today_start.isoformat(),
            end_display,
        )

        try:
            energy_data = await self._api.async_get_energy_measures(
                rooms_for_api, date_begin, date_end, scale=scale
            )
        except RateLimitError:
            _LOGGER.warning(
                "Rate limited while fetching energy data, will retry on next update"
            )
            return
        except (APIError, CannotConnect) as err:
            _LOGGER.warning(
                "Failed to fetch energy data: %s, will retry on next update", err
            )
            return

        # Cache the results (for daily mode) and populate room.energy
        # API returns Wh, convert to kWh for display
        if not is_realtime:
            self._energy_cache.clear()
            self._energy_cache["_date"] = today_iso

        for room_id, room in data_by_room.items():
            wh = energy_data.get(room_id, 0.0)
            kwh = wh / 1000.0  # Convert Wh to kWh
            if not is_realtime:
                self._energy_cache[room_id] = kwh
            room.energy = kwh

        _LOGGER.debug("Energy data fetched (scale=%s): %s", scale, {k: f"{v:.3f} kWh" for k, v in energy_data.items()})
