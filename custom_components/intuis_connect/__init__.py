"""Setup for Intuis Connect (v1.9.0)."""
from __future__ import annotations

import datetime
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.storage import Store

from .intuis_api.api import IntuisAPI, InvalidAuth, CannotConnect
from .utils.const import (
    DOMAIN,
    CONF_REFRESH_TOKEN,
    CONF_HOME_ID,
    CONF_HOME_NAME,
    CONF_IMPORT_HISTORY,
    CONF_IMPORT_HISTORY_DAYS,
    DEFAULT_UPDATE_INTERVAL,
)
from .entity.intuis_entity import IntuisDataUpdateCoordinator
from .history_import import (
    HistoryImportManager,
    async_import_energy_history,
)
from .intuis_data import IntuisData
from .services import (
    async_generate_services_yaml,
    async_register_services,
    SERVICE_SWITCH_SCHEDULE,
    SERVICE_REFRESH_SCHEDULES,
    SERVICE_SET_SCHEDULE_SLOT,
    SERVICE_SET_ZONE_TEMPERATURE,
    SERVICE_IMPORT_ENERGY_HISTORY,
    ATTR_SCHEDULE_NAME,
    ATTR_DAY,
    ATTR_START_DAY,
    ATTR_END_DAY,
    ATTR_START_TIME,
    ATTR_END_TIME,
    ATTR_ZONE_NAME,
    ATTR_ROOM_NAME,
    ATTR_TEMPERATURE,
    ATTR_DAYS,
)

_LOGGER = logging.getLogger(__name__)

# Storage for persisting overrides across restarts
STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.overrides"

PLATFORMS: list[Platform] = [
    Platform.CALENDAR,
    Platform.CLIMATE,
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.SELECT,
    Platform.NUMBER,
]


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

    # ---------- generate dynamic services.yaml -------------------------------------
    await async_generate_services_yaml(hass, intuis_home)

    # ---------- shared overrides (sticky intents) with persistence -----------------
    # Set up storage for persisting overrides across restarts
    store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry.entry_id}")

    # Load persisted overrides
    stored_data = await store.async_load()
    overrides: dict[str, dict] = stored_data.get("overrides", {}) if stored_data else {}

    if overrides:
        _LOGGER.info("Loaded %d persisted overrides from storage", len(overrides))

    # Callback to save overrides to storage
    async def save_overrides() -> None:
        """Persist overrides to storage."""
        await store.async_save({"overrides": overrides})
        _LOGGER.debug("Saved %d overrides to storage", len(overrides))

    # ---------- setup coordinator --------------------------------------------------
    # Callback to get current options from config entry
    def get_options() -> dict:
        return dict(entry.options)

    intuis_data = IntuisData(
        intuis_api,
        intuis_home,
        overrides,
        get_options,
        save_overrides_callback=save_overrides,
    )

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
        "save_overrides": save_overrides,
    }
    _LOGGER.debug("Stored data for entry %s", entry.entry_id)

    # ---------- setup platforms ----------------------------------------------------
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # ---------- register services -------------------------------------------------
    await async_register_services(hass, entry)

    # ---------- trigger historical import if requested ----------------------------
    import_history = entry.options.get(CONF_IMPORT_HISTORY, False)
    import_days = entry.options.get(CONF_IMPORT_HISTORY_DAYS, 0)

    if import_history and import_days > 0:
        _LOGGER.info(
            "Historical energy import requested for %d days, starting in background",
            import_days,
        )

        # Create import manager
        manager = HistoryImportManager(hass, entry.entry_id)
        await manager.async_load()

        # Store manager for potential service access
        if "import_managers" not in hass.data[DOMAIN]:
            hass.data[DOMAIN]["import_managers"] = {}
        hass.data[DOMAIN]["import_managers"][entry.entry_id] = manager

        # Start import in background task
        hass.async_create_task(
            async_import_energy_history(
                hass=hass,
                api=intuis_api,
                intuis_home=intuis_home,
                manager=manager,
                days=import_days,
                room_filter=None,
                home_id=entry.data["home_id"],
            )
        )

        # Clear the import flag so it doesn't run again on reload
        new_options = {**entry.options, CONF_IMPORT_HISTORY: False}
        hass.config_entries.async_update_entry(entry, options=new_options)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading entry %s", entry.entry_id)
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
        _LOGGER.debug("Unloaded entry %s", entry.entry_id)
    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entry to a newer version.

    Handles migration from V2 to V3:
    - Adds CONF_HOME_NAME if missing (for multi-home support)
    """
    _LOGGER.debug("Migrating entry %s from version %s", entry.entry_id, entry.version)

    if entry.version < 3:
        # V2 -> V3: Add home_name if missing
        new_data = {**entry.data}

        if CONF_HOME_NAME not in new_data or not new_data.get(CONF_HOME_NAME):
            home_id = new_data.get(CONF_HOME_ID, "")
            home_name = None

            # Try to fetch the home name from the API
            try:
                session = async_get_clientsession(hass)
                api = IntuisAPI(session, home_id=home_id)
                api.refresh_token = new_data.get(CONF_REFRESH_TOKEN)
                await api.async_refresh_access_token()

                homes = await api.async_get_all_homes()
                for home in homes:
                    if home["id"] == home_id:
                        home_name = home["name"]
                        break

                _LOGGER.info(
                    "Migration: Fetched home name '%s' for home %s",
                    home_name,
                    home_id,
                )
            except Exception as err:
                _LOGGER.warning(
                    "Migration: Could not fetch home name from API: %s",
                    err,
                )

            # Fall back to truncated home_id if API fails
            if not home_name:
                home_name = f"Home {home_id[:8]}" if home_id else "Unknown Home"
                _LOGGER.info(
                    "Migration: Using fallback home name '%s'",
                    home_name,
                )

            new_data[CONF_HOME_NAME] = home_name

        hass.config_entries.async_update_entry(
            entry,
            data=new_data,
            version=3,
        )
        _LOGGER.info(
            "Migrated entry %s to version 3 with home_name: %s",
            entry.entry_id,
            new_data.get(CONF_HOME_NAME),
        )

    return True
