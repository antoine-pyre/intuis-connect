"""Setup for Intuis Connect (v1.3.0)."""
from __future__ import annotations

import datetime
import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import IntuisAPI, CannotConnect, InvalidAuth
from .const import (
    DOMAIN,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_REFRESH_TOKEN,
    CONF_HOME_ID,
)
from .data import IntuisData

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["calendar", "climate", "binary_sensor", "sensor"]

SERVICE_CLEAR_OVERRIDE = "clear_override"
ATTR_ROOM_ID = "room_id"

CLEAR_OVERRIDE_SCHEMA = vol.Schema({vol.Required(ATTR_ROOM_ID): str})


async def update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """Handle options update."""
    _LOGGER.debug("Reloading entry %s due to options update", entry.entry_id)
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    _LOGGER.debug("async_setup")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Intuis Connect from a config entry."""
    _LOGGER.debug("Setting up entry %s", entry.entry_id)
    hass.data.setdefault(DOMAIN, {})
    entry.async_on_unload(entry.add_update_listener(update_listener))

    # ---------- setup API ----------------------------------------------------------
    session = async_get_clientsession(hass)
    api = IntuisAPI(session)
    api.home_id = entry.data[CONF_HOME_ID]
    api.refresh_token = entry.data[CONF_REFRESH_TOKEN]

    # ---------- setup coordinator --------------------------------------------------
    intuis_data = IntuisData(api)

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=intuis_data.async_update,
        update_interval=datetime.timedelta(minutes=5),
    )
    await coordinator.async_config_entry_first_refresh()

    # ---------- store everything ---------------------------------------------------
    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
    }
    _LOGGER.debug("Stored data for entry %s", entry.entry_id)

    # ---------- setup platforms ----------------------------------------------------
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _LOGGER.debug("Unloading entry %s", entry.entry_id)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        _LOGGER.debug("Unloaded entry %s", entry.entry_id)
    return unload_ok
