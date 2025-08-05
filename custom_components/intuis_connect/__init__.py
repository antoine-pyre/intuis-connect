"""Setup for Intuis Connect (v1.3.0)."""
from __future__ import annotations

import datetime
import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import IntuisAPI, InvalidAuth, CannotConnect
from .const import (
    DOMAIN,
    CONF_HOME_ID,
    CONF_REFRESH_TOKEN,
)
from .entity.intuis_entity import IntuisDataUpdateCoordinator
from .entity.intuis_schedule import IntuisSchedule
from .intuis_data import IntuisData, IntuisRoomDefinition

_LOGGER = logging.getLogger(__name__)

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

    home_data = await intuis_api.async_get_homes_data()
    # build a static map of room_id → room_name
    rooms_definitions: dict[str, IntuisRoomDefinition] = {
        r["id"]: IntuisRoomDefinition.from_dict(r)
        for r in home_data["rooms"]
    }
    _LOGGER.debug("Rooms definitions: %s", rooms_definitions)

    # --- pull the active schedule ---
    _LOGGER.debug("Fetching active schedules")
    _LOGGER.debug("schedules: %s", home_data.get("schedules", []))
    schedules = [IntuisSchedule.from_dict(t) for t in home_data.get("schedules", [])]

    # ---------- setup coordinator --------------------------------------------------
    intuis_data = IntuisData(intuis_api, rooms_definitions, schedules)

    coordinator: IntuisDataUpdateCoordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=intuis_data.async_update,
        update_interval=datetime.timedelta(minutes=5),
    )
    await coordinator.async_config_entry_first_refresh()

    # ---------- store everything ---------------------------------------------------
    _LOGGER.debug("Storing data for entry %s", entry.entry_id)
    hass.data[DOMAIN][entry.entry_id] = {
        "api": intuis_api,
        "coordinator": coordinator,
        "home_id": intuis_api.home_id,
        "rooms_definitions": rooms_definitions,
    }
    _LOGGER.debug("Stored data for entry %s", entry.entry_id)

    # ---------- setup platforms ----------------------------------------------------
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading entry %s", entry.entry_id)
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
        _LOGGER.debug("Unloaded entry %s", entry.entry_id)
    return unload_ok
