"""Historical energy data import for Intuis Connect.

This module provides functionality to import historical energy data from the
Intuis cloud API into Home Assistant's statistics database. The imported data
appears on the existing sensor entities, not as separate external statistics.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import TYPE_CHECKING

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_import_statistics,
    get_last_statistics,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .utils.const import DOMAIN

if TYPE_CHECKING:
    from .intuis_api.api import IntuisAPI
    from .entity.intuis_home import IntuisHome

_LOGGER = logging.getLogger(__name__)

# Storage version for import state
STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.history_import"

# Import configuration
DEFAULT_HISTORY_DAYS = 365
MAX_HISTORY_DAYS = 730
API_DELAY_SECONDS = 2.0  # Delay between API calls to avoid rate limiting


def slugify(text: str) -> str:
    """Convert text to a slug suitable for entity IDs."""
    # Convert to lowercase
    text = text.lower()
    # Replace spaces and hyphens with underscores
    text = re.sub(r'[\s\-]+', '_', text)
    # Remove any characters that aren't alphanumeric or underscores
    text = re.sub(r'[^a-z0-9_]', '', text)
    # Remove consecutive underscores
    text = re.sub(r'_+', '_', text)
    # Remove leading/trailing underscores
    text = text.strip('_')
    return text


class HistoryImportManager:
    """Manages persistent state for energy history import."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize the import manager."""
        self.hass = hass
        self.entry_id = entry_id
        self.store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}_{entry_id}")
        self._state: dict = {}
        self._running = False
        self._cancelled = False

        # Progress tracking
        self.status = "idle"
        self.current_room: str | None = None
        self.rooms_completed = 0
        self.total_rooms = 0
        self.days_imported = 0
        self.total_days = 0
        self.last_error: str | None = None

    async def async_load(self) -> None:
        """Load import state from storage."""
        data = await self.store.async_load()
        self._state = data or {
            "rooms": {},  # room_id -> {"last_imported_day": int, "cumulative_sum": float}
        }

    async def async_save(self) -> None:
        """Save import state to storage."""
        await self.store.async_save(self._state)

    def get_room_progress(self, room_id: str) -> dict:
        """Get progress for a specific room."""
        return self._state.get("rooms", {}).get(room_id, {
            "last_imported_day": 0,
            "cumulative_sum": 0.0,
        })

    def update_room_progress(
        self, room_id: str, last_day: int, cumulative_sum: float
    ) -> None:
        """Update progress for a specific room."""
        if "rooms" not in self._state:
            self._state["rooms"] = {}
        self._state["rooms"][room_id] = {
            "last_imported_day": last_day,
            "cumulative_sum": cumulative_sum,
        }

    def clear_room_progress(self, room_id: str) -> None:
        """Clear progress for a specific room to allow re-import."""
        if "rooms" in self._state and room_id in self._state["rooms"]:
            del self._state["rooms"][room_id]

    def cancel(self) -> None:
        """Request cancellation of the running import."""
        self._cancelled = True

    @property
    def is_running(self) -> bool:
        """Check if import is currently running."""
        return self._running


async def get_entity_last_sum(
    hass: HomeAssistant, entity_id: str
) -> float:
    """Get the last sum value from existing statistics for an entity.

    Returns 0.0 if no statistics exist.
    """
    try:
        # Run in executor since get_last_statistics is synchronous
        last_stats = await get_instance(hass).async_add_executor_job(
            get_last_statistics,
            hass,
            1,  # number of stats to retrieve
            entity_id,
            True,  # convert_units
            {"sum"},  # types to retrieve
        )

        if last_stats and entity_id in last_stats:
            stats_list = last_stats[entity_id]
            if stats_list:
                return stats_list[0].get("sum", 0.0) or 0.0

    except Exception as err:
        _LOGGER.warning(
            "Could not get last statistics for %s: %s", entity_id, err
        )

    return 0.0


async def async_import_energy_history(
    hass: HomeAssistant,
    api: "IntuisAPI",
    intuis_home: "IntuisHome",
    manager: HistoryImportManager,
    days: int = DEFAULT_HISTORY_DAYS,
    room_filter: str | None = None,
) -> dict:
    """Import historical energy data into Home Assistant statistics.

    This function fetches daily energy consumption for the configured number
    of days and imports it as statistics for existing sensor entities.

    Args:
        hass: Home Assistant instance.
        api: Intuis API client.
        intuis_home: Intuis home data.
        manager: Import manager for state persistence.
        days: Number of days of history to import (1-730).
        room_filter: Optional room name to import only that room.

    Returns:
        Dict with import results: rooms_imported, total_energy, errors.
    """
    if manager.is_running:
        _LOGGER.warning("Import already running, ignoring request")
        return {"error": "Import already running"}

    manager._running = True
    manager._cancelled = False
    manager.status = "importing"
    manager.last_error = None

    # Clamp days to valid range
    days = max(1, min(days, MAX_HISTORY_DAYS))

    # Build list of rooms to import
    rooms_data = intuis_home.rooms
    rooms_to_import: list[dict] = []

    for room_id, room_def in rooms_data.items():
        room_name = room_def.name if hasattr(room_def, 'name') else str(room_id)

        # Apply room filter if specified
        if room_filter and room_name.lower() != room_filter.lower():
            continue

        # We need bridge_id for API calls - get from coordinator data
        # For now, we'll store it when we have access to the full room objects
        rooms_to_import.append({
            "id": room_id,
            "name": room_name,
        })

    if not rooms_to_import:
        manager._running = False
        manager.status = "idle"
        if room_filter:
            return {"error": f"Room '{room_filter}' not found"}
        return {"error": "No rooms found"}

    manager.total_rooms = len(rooms_to_import)
    manager.rooms_completed = 0
    manager.total_days = days

    _LOGGER.info(
        "Starting energy history import for %d rooms, %d days",
        len(rooms_to_import),
        days,
    )

    now = datetime.now(timezone.utc)
    results = {
        "rooms_imported": 0,
        "total_energy_kwh": 0.0,
        "errors": [],
    }

    try:
        for room_info in rooms_to_import:
            if manager._cancelled:
                _LOGGER.info("Import cancelled by user")
                manager.status = "cancelled"
                break

            room_id = room_info["id"]
            room_name = room_info["name"]
            manager.current_room = room_name

            # Build entity_id for this room's energy sensor
            room_slug = slugify(room_name)
            entity_id = f"sensor.{room_slug}_energy"

            # Check if entity exists
            if not hass.states.get(entity_id):
                _LOGGER.warning(
                    "Energy sensor %s does not exist, skipping room %s",
                    entity_id,
                    room_name,
                )
                results["errors"].append(f"Entity {entity_id} not found")
                continue

            _LOGGER.info(
                "Importing energy history for room: %s (entity: %s)",
                room_name,
                entity_id,
            )

            # Get existing sum to continue from
            existing_sum = await get_entity_last_sum(hass, entity_id)
            _LOGGER.debug(
                "Existing sum for %s: %.3f kWh", entity_id, existing_sum
            )

            # Collect daily statistics
            statistics: list[StatisticData] = []
            cumulative_sum = existing_sum
            manager.days_imported = 0

            for day_offset in range(days, 0, -1):
                if manager._cancelled:
                    break

                target_date = now - timedelta(days=day_offset)
                day_start = datetime.combine(
                    target_date.date(),
                    datetime.min.time(),
                    tzinfo=timezone.utc
                )
                day_end = datetime.combine(
                    target_date.date(),
                    datetime.max.time(),
                    tzinfo=timezone.utc
                )

                try:
                    # Fetch energy for this room and day
                    energy_data = await api.async_get_energy_measures(
                        [{"id": room_id, "bridge": ""}],  # bridge not needed for this endpoint
                        int(day_start.timestamp()),
                        int(day_end.timestamp()),
                        scale="1day"
                    )

                    # API returns Wh, convert to kWh
                    day_energy_wh = energy_data.get(room_id, 0.0)
                    day_energy_kwh = day_energy_wh / 1000.0

                    if day_energy_kwh > 0:
                        cumulative_sum += day_energy_kwh
                        statistics.append(
                            StatisticData(
                                start=day_start,
                                state=day_energy_kwh,
                                sum=cumulative_sum,
                            )
                        )
                        _LOGGER.debug(
                            "%s day %s: %.3f kWh (total: %.3f kWh)",
                            room_name,
                            target_date.date(),
                            day_energy_kwh,
                            cumulative_sum,
                        )

                    manager.days_imported = days - day_offset + 1

                    # Delay to avoid rate limiting
                    await asyncio.sleep(API_DELAY_SECONDS)

                except Exception as err:
                    error_str = str(err)
                    if "429" in error_str:
                        _LOGGER.warning(
                            "Rate limited while importing %s. Saving progress.",
                            room_name,
                        )
                        manager.status = "rate_limited"
                        manager.last_error = "Rate limited by API"
                        # Save what we have and stop
                        break
                    else:
                        _LOGGER.warning(
                            "Failed to fetch energy for %s on %s: %s",
                            room_name,
                            target_date.date(),
                            err,
                        )
                        # Continue to next day
                        await asyncio.sleep(API_DELAY_SECONDS)

            # Import collected statistics for this room
            if statistics:
                try:
                    # Use StatisticMeanType if available (HA 2025.11+)
                    try:
                        from homeassistant.components.recorder.models import StatisticMeanType
                        metadata = StatisticMetaData(
                            source="recorder",
                            statistic_id=entity_id,
                            name=f"{room_name} Energy",
                            unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
                            has_sum=True,
                            mean_type=StatisticMeanType.NONE,
                        )
                    except ImportError:
                        # Fallback for older HA versions
                        metadata = StatisticMetaData(
                            source="recorder",
                            statistic_id=entity_id,
                            name=f"{room_name} Energy",
                            unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
                            has_mean=False,
                            has_sum=True,
                        )

                    async_import_statistics(hass, metadata, statistics)

                    results["rooms_imported"] += 1
                    results["total_energy_kwh"] += cumulative_sum - existing_sum

                    _LOGGER.info(
                        "Imported %d days of energy history for %s (%.3f kWh)",
                        len(statistics),
                        room_name,
                        cumulative_sum - existing_sum,
                    )

                except Exception as err:
                    _LOGGER.error(
                        "Failed to import statistics for %s: %s",
                        room_name,
                        err,
                    )
                    results["errors"].append(
                        f"Failed to import {room_name}: {err}"
                    )

            manager.rooms_completed += 1
            await manager.async_save()

            if manager.status == "rate_limited":
                break

    finally:
        manager._running = False
        if manager.status not in ("cancelled", "rate_limited"):
            manager.status = "completed"
        manager.current_room = None

    _LOGGER.info(
        "Energy history import finished: %d rooms, %.3f kWh total",
        results["rooms_imported"],
        results["total_energy_kwh"],
    )

    return results
