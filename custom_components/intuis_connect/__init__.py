"""Setup for Intuis Connect (v1.3.0)."""
from __future__ import annotations

import asyncio
import datetime
import json
import logging
from datetime import timezone
from pathlib import Path

import voluptuous as vol
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
    statistics_during_period,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .entity.intuis_home import IntuisHome
from .intuis_api.api import IntuisAPI, InvalidAuth, CannotConnect, APIError
from .utils.const import (
    DOMAIN,
    CONF_HOME_ID,
    CONF_REFRESH_TOKEN,
    CONF_IMPORT_HISTORY,
    CONF_HISTORY_DAYS,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_IMPORT_HISTORY,
    DEFAULT_HISTORY_DAYS,
)
from .entity.intuis_entity import IntuisDataUpdateCoordinator
from .entity.intuis_schedule import IntuisSchedule
from .intuis_data import IntuisData

_LOGGER = logging.getLogger(__name__)

# Storage version for import state
STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.import_state"

PLATFORMS: list[Platform] = [
    # Platform.CALENDAR,
    Platform.CLIMATE,
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
]

SERVICE_CLEAR_OVERRIDE = "clear_override"
ATTR_ROOM_ID = "room_id"

CLEAR_OVERRIDE_SCHEMA = vol.Schema({vol.Required(ATTR_ROOM_ID): str})


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    _LOGGER.debug("Reloading entry %s due to options update", entry.entry_id)
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Intuis Connect component."""
    _LOGGER.debug("async_setup")
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Intuis Connect from a config entry."""
    _LOGGER.debug("Setting up entry %s", entry.entry_id)
    hass.data.setdefault(DOMAIN, {})
    entry.async_on_unload(entry.add_update_listener(update_listener))

    # ---------- setup API ----------------------------------------------------------
    session = async_get_clientsession(hass)
    intuis_api = IntuisAPI(session, home_id=entry.data["home_id"])
    intuis_api.home_id = entry.data["home_id"]
    intuis_api.refresh_token = entry.data[CONF_REFRESH_TOKEN]

    try:
        await intuis_api.async_refresh_access_token()
    except InvalidAuth as err:
        raise ConfigEntryAuthFailed from err
    except CannotConnect as err:
        raise ConfigEntryNotReady from err

    intuis_home = await intuis_api.async_get_homes_data()
    _LOGGER.debug("Intuis home: %s", intuis_home.__str__())

    # ---------- shared overrides (sticky intents) ----------------------------------
    overrides: dict[str, dict] = {}

    # ---------- setup coordinator --------------------------------------------------
    # Callback to get current options from config entry
    def get_options() -> dict:
        return dict(entry.options)

    intuis_data = IntuisData(intuis_api, intuis_home, overrides, get_options)

    coordinator: IntuisDataUpdateCoordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=intuis_data.async_update,
        update_interval=datetime.timedelta(minutes=DEFAULT_UPDATE_INTERVAL),
    )
    await coordinator.async_config_entry_first_refresh()

    # ---------- store everything ---------------------------------------------------
    _LOGGER.debug("Storing data for entry %s", entry.entry_id)
    hass.data[DOMAIN][entry.entry_id] = {
        "api": intuis_api,
        "coordinator": coordinator,
        "intuis_home": intuis_home,
        "overrides": overrides,
    }
    _LOGGER.debug("Stored data for entry %s", entry.entry_id)

    # ---------- setup platforms ----------------------------------------------------
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # ---------- import energy history (runs in background) ----------------------
    # Pass the coordinator data which has IntuisRoom objects with bridge_ids
    hass.async_create_task(
        async_import_energy_history(hass, entry, intuis_api, coordinator.data)
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading entry %s", entry.entry_id)
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
        _LOGGER.debug("Unloaded entry %s", entry.entry_id)
    return unload_ok


class HistoryImportManager:
    """Manages persistent state for energy history import."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the import manager."""
        self.hass = hass
        self.entry = entry
        self.store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}_{entry.entry_id}")
        self._state: dict = {}
        self._running = False

    async def async_load(self) -> None:
        """Load import state from storage."""
        data = await self.store.async_load()
        self._state = data or {
            "import_requested": False,
            "import_completed": False,
            "history_days": 0,
            "rooms": {},  # room_id -> {"last_imported_day": int, "completed": bool, "cumulative_sum": float}
        }

    async def async_save(self) -> None:
        """Save import state to storage."""
        await self.store.async_save(self._state)

    def is_import_needed(self) -> bool:
        """Check if import is needed (requested but not completed)."""
        return self._state.get("import_requested", False) and not self._state.get("import_completed", False)

    def mark_import_requested(self, history_days: int) -> None:
        """Mark that an import has been requested."""
        self._state["import_requested"] = True
        self._state["import_completed"] = False
        self._state["history_days"] = history_days
        self._state["rooms"] = {}

    def mark_import_completed(self) -> None:
        """Mark import as fully completed."""
        self._state["import_completed"] = True

    def get_room_progress(self, room_id: str) -> dict:
        """Get progress for a specific room."""
        return self._state.get("rooms", {}).get(room_id, {
            "last_imported_day": 0,
            "completed": False,
            "cumulative_sum": 0.0,
        })

    def update_room_progress(self, room_id: str, last_day: int, cumulative_sum: float, completed: bool = False) -> None:
        """Update progress for a specific room."""
        if "rooms" not in self._state:
            self._state["rooms"] = {}
        self._state["rooms"][room_id] = {
            "last_imported_day": last_day,
            "completed": completed,
            "cumulative_sum": cumulative_sum,
        }

    @property
    def history_days(self) -> int:
        """Get the configured history days."""
        return self._state.get("history_days", DEFAULT_HISTORY_DAYS)


async def async_import_energy_history(
    hass: HomeAssistant,
    entry: ConfigEntry,
    api: IntuisAPI,
    coordinator_data: dict,
) -> None:
    """Import historical energy data into Home Assistant statistics.

    This function fetches daily energy consumption for the configured number
    of days and imports it as external statistics for the energy dashboard.
    It persists progress and can resume after restarts or rate limiting.
    """
    import_history = entry.options.get(CONF_IMPORT_HISTORY, DEFAULT_IMPORT_HISTORY)
    history_days = entry.options.get(CONF_HISTORY_DAYS, DEFAULT_HISTORY_DAYS)

    # Initialize import manager
    manager = HistoryImportManager(hass, entry)
    await manager.async_load()

    # Check if we need to start a new import or resume an existing one
    if import_history and not manager._state.get("import_requested"):
        # New import requested
        _LOGGER.info("New energy history import requested for %d days", history_days)
        manager.mark_import_requested(history_days)
        await manager.async_save()
    elif not import_history:
        _LOGGER.debug("History import not enabled, skipping")
        return

    if manager._state.get("import_completed"):
        _LOGGER.debug("History import already completed")
        return

    if manager.is_import_needed():
        _LOGGER.info("Resuming/starting energy history import for %d days", manager.history_days)
    else:
        return

    # Get list of rooms with their bridge IDs from coordinator data
    rooms_data = coordinator_data.get("rooms", {})
    rooms_for_api: list[dict[str, str]] = []
    room_names: dict[str, str] = {}

    for room_id, room in rooms_data.items():
        if room.bridge_id:
            rooms_for_api.append({"id": room.id, "bridge": room.bridge_id})
            room_names[room.id] = room.name
        else:
            _LOGGER.debug("Room %s has no bridge_id, skipping history import", room.name)

    if not rooms_for_api:
        _LOGGER.warning("No rooms with bridge_id found, cannot import history")
        return

    now = datetime.datetime.now(timezone.utc)
    all_rooms_completed = True
    rate_limited = False

    # Import data for each room
    for room_info in rooms_for_api:
        room_id = room_info["id"]
        room_name = room_names.get(room_id, room_id)

        # Get existing progress for this room
        progress = manager.get_room_progress(room_id)
        if progress.get("completed"):
            _LOGGER.debug("Room %s already completed, skipping", room_name)
            continue

        # Create statistic ID for external statistics (format: domain:identifier)
        # These will appear in the Energy Dashboard under "Individual devices"
        room_name_slug = room_name.lower().replace(" ", "_").replace("-", "_")
        statistic_id = f"{DOMAIN}:{room_name_slug}_energy"

        # Resume from last imported day
        start_day = progress.get("last_imported_day", 0) + 1
        cumulative_sum = progress.get("cumulative_sum", 0.0)

        if start_day > manager.history_days:
            # This room is done
            manager.update_room_progress(room_id, manager.history_days, cumulative_sum, completed=True)
            await manager.async_save()
            continue

        _LOGGER.info(
            "Importing energy history for room: %s (days %d-%d)",
            room_name, start_day, manager.history_days
        )

        # Collect daily statistics
        statistics: list[StatisticData] = []
        last_successful_day = start_day - 1

        for days_ago in range(manager.history_days - start_day + 1, 0, -1):
            current_day = manager.history_days - days_ago + 1

            target_date = now - datetime.timedelta(days=days_ago)
            day_start = datetime.datetime.combine(
                target_date.date(),
                datetime.time.min,
                tzinfo=timezone.utc
            )
            day_end = datetime.datetime.combine(
                target_date.date(),
                datetime.time.max,
                tzinfo=timezone.utc
            )

            try:
                energy_data = await api.async_get_energy_measures(
                    [room_info],
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
                        "Room %s day %s: %.3f kWh (total: %.3f kWh)",
                        room_name,
                        target_date.date(),
                        day_energy_kwh,
                        cumulative_sum
                    )

                last_successful_day = current_day

                # Add delay to avoid rate limiting (429 errors)
                await asyncio.sleep(1.5)

            except APIError as e:
                if "429" in str(e):
                    _LOGGER.warning(
                        "Rate limited while importing %s day %d. Saving progress and will resume later.",
                        room_name, current_day
                    )
                    rate_limited = True
                    # Save progress before stopping
                    manager.update_room_progress(room_id, last_successful_day, cumulative_sum)
                    await manager.async_save()
                    break
                else:
                    _LOGGER.warning(
                        "Failed to fetch energy for room %s on %s: %s",
                        room_name, target_date.date(), e
                    )
                    # Continue to next day after non-rate-limit error
                    await asyncio.sleep(2.0)

            except Exception as e:
                _LOGGER.warning(
                    "Unexpected error fetching energy for room %s on %s: %s",
                    room_name, target_date.date(), e
                )
                await asyncio.sleep(2.0)

        # Import collected statistics
        if statistics:
            metadata = StatisticMetaData(
                has_mean=False,
                has_sum=True,
                mean_type=None,
                name=f"{room_name} Energy",
                source=DOMAIN,
                statistic_id=statistic_id,
                unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            )
            async_add_external_statistics(hass, metadata, statistics)
            _LOGGER.info(
                "Imported %d days of energy history for %s (%.3f kWh)",
                len(statistics), room_name, cumulative_sum
            )

        # Check if this room is complete
        if not rate_limited and last_successful_day >= manager.history_days:
            manager.update_room_progress(room_id, manager.history_days, cumulative_sum, completed=True)
            _LOGGER.info("Room %s import completed", room_name)
        else:
            manager.update_room_progress(room_id, last_successful_day, cumulative_sum)
            all_rooms_completed = False

        await manager.async_save()

        if rate_limited:
            all_rooms_completed = False
            break

    # Check if all rooms are done
    if all_rooms_completed:
        manager.mark_import_completed()
        await manager.async_save()
        _LOGGER.info("Energy history import completed for all rooms")
    elif rate_limited:
        _LOGGER.info("Energy history import paused due to rate limiting. Will resume on next restart.")
    else:
        _LOGGER.info("Energy history import in progress. Some rooms pending.")
