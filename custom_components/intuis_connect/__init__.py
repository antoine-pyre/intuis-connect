"""Setup for Intuis Connect (v1.6.0)."""
from __future__ import annotations

import datetime
import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .entity.intuis_home import IntuisHome
from .intuis_api.api import IntuisAPI, InvalidAuth, CannotConnect
from .utils.const import (
    DOMAIN,
    CONF_HOME_ID,
    CONF_REFRESH_TOKEN,
    DEFAULT_UPDATE_INTERVAL,
)
from .entity.intuis_entity import IntuisDataUpdateCoordinator
from .entity.intuis_schedule import IntuisSchedule, IntuisThermSchedule
from .intuis_data import IntuisData

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.CALENDAR,
    Platform.CLIMATE,
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.SELECT,
]

# Service names
SERVICE_CLEAR_OVERRIDE = "clear_override"
SERVICE_SWITCH_SCHEDULE = "switch_schedule"
SERVICE_REFRESH_SCHEDULES = "refresh_schedules"

# Service attributes
ATTR_ROOM_ID = "room_id"
ATTR_SCHEDULE_ID = "schedule_id"
ATTR_SCHEDULE_NAME = "schedule_name"

# Service schemas
CLEAR_OVERRIDE_SCHEMA = vol.Schema({vol.Required(ATTR_ROOM_ID): str})
SWITCH_SCHEDULE_SCHEMA = vol.Schema({
    vol.Optional(ATTR_SCHEDULE_ID): str,
    vol.Optional(ATTR_SCHEDULE_NAME): str,
})
REFRESH_SCHEDULES_SCHEMA = vol.Schema({})


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

    # ---------- register services -------------------------------------------------
    await _async_register_services(hass, entry)

    return True


async def _async_register_services(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register Intuis Connect services."""

    async def async_handle_switch_schedule(call: ServiceCall) -> None:
        """Handle switch_schedule service call."""
        schedule_id = call.data.get(ATTR_SCHEDULE_ID)
        schedule_name = call.data.get(ATTR_SCHEDULE_NAME)

        if not schedule_id and not schedule_name:
            _LOGGER.error("Either schedule_id or schedule_name must be provided")
            return

        # Get the first (and usually only) config entry
        for entry_id, data in hass.data[DOMAIN].items():
            if not isinstance(data, dict):
                continue

            api: IntuisAPI = data.get("api")
            intuis_home: IntuisHome = data.get("intuis_home")
            coordinator = data.get("coordinator")

            if not api or not intuis_home:
                continue

            # Find the schedule by ID or name
            target_schedule = None
            for schedule in intuis_home.schedules:
                if isinstance(schedule, IntuisThermSchedule):
                    if schedule_id and schedule.id == schedule_id:
                        target_schedule = schedule
                        break
                    if schedule_name and schedule.name == schedule_name:
                        target_schedule = schedule
                        break

            if not target_schedule:
                _LOGGER.error(
                    "Schedule not found: id=%s, name=%s",
                    schedule_id,
                    schedule_name
                )
                return

            _LOGGER.info(
                "Switching to schedule: %s (ID: %s)",
                target_schedule.name,
                target_schedule.id
            )

            try:
                await api.async_switch_schedule(intuis_home.id, target_schedule.id)
                # Update local state
                for s in intuis_home.schedules:
                    if isinstance(s, IntuisThermSchedule):
                        s.selected = (s.id == target_schedule.id)
                # Refresh coordinator
                if coordinator:
                    await coordinator.async_request_refresh()
            except Exception as err:
                _LOGGER.error("Failed to switch schedule: %s", err)
                raise

            break

    async def async_handle_refresh_schedules(call: ServiceCall) -> None:
        """Handle refresh_schedules service call."""
        for entry_id, data in hass.data[DOMAIN].items():
            if not isinstance(data, dict):
                continue

            coordinator = data.get("coordinator")
            if coordinator:
                _LOGGER.info("Refreshing schedule data")
                await coordinator.async_request_refresh()
                break

    # Only register services once
    if not hass.services.has_service(DOMAIN, SERVICE_SWITCH_SCHEDULE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SWITCH_SCHEDULE,
            async_handle_switch_schedule,
            schema=SWITCH_SCHEDULE_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_REFRESH_SCHEDULES):
        hass.services.async_register(
            DOMAIN,
            SERVICE_REFRESH_SCHEDULES,
            async_handle_refresh_schedules,
            schema=REFRESH_SCHEDULES_SCHEMA,
        )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading entry %s", entry.entry_id)
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
        _LOGGER.debug("Unloaded entry %s", entry.entry_id)
    return unload_ok
