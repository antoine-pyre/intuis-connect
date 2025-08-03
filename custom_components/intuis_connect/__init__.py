"""The Intuis Connect integration."""
from __future__ import annotations

import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import IntuisAPI, CannotConnect, InvalidAuth, APIError
from .const import DOMAIN

LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    username = entry.data.get("username")
    refresh_token = entry.data.get("refresh_token")
    home_id = entry.data.get("home_id")
    session = hass.helpers.aiohttp_client.async_get_clientsession(hass)
    api = IntuisAPI(session, home_id=home_id)
    try:
        api.set_tokens("", refresh_token, 0)
        await api.async_refresh_access_token()
    except (CannotConnect, InvalidAuth):
        raise
    home_data = await api.async_get_homes_data()
    room_dict = {r["id"]: r.get("name", f"Room {r['id']}") for r in home_data.get("rooms", [])}

    async def _async_update():
        try:
            status = await api.async_get_home_status()
        except (CannotConnect, APIError) as err:
            raise UpdateFailed(str(err)) from err
        data_by_room = {}
        rooms = status.get("body", {}).get("home", {}).get("rooms", [])
        modules = status.get("body", {}).get("home", {}).get("modules", [])
        modules_by_room = {}
        for mod in modules:
            modules_by_room.setdefault(mod.get("room_id"), []).append(mod)
        for room in rooms:
            rid = room["id"]
            info = {
                "temperature": room.get("therm_measured_temperature"),
                "target_temperature": room.get("therm_setpoint_temperature"),
                "mode": room.get("therm_setpoint_mode"),
                "heating": False,
                "open_window": False,
                "presence": False
            }
            for mod in modules_by_room.get(rid, []):
                if mod.get("heating_power_request", 0) > 0:
                    info["heating"] = True
                if mod.get("open_window_detected"):
                    info["open_window"] = True
                if mod.get("presence"):
                    info["presence"] = True
            data_by_room[rid] = info
        return data_by_room

    coordinator = DataUpdateCoordinator(
        hass, LOGGER,
        name="intuis_connect",
        update_method=_async_update,
        update_interval=None
    )
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
        "rooms": room_dict,
        "home_id": api.home_id
    }
    await hass.config_entries.async_forward_entry_setups(entry, ["climate", "binary_sensor"])
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["climate", "binary_sensor"])
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
