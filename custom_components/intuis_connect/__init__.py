"""Set up Intuis Connect integration."""
from __future__ import annotations
import logging, datetime
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import IntuisAPI, CannotConnect, InvalidAuth, APIError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    username = entry.data["username"]
    refresh_token = entry.data["refresh_token"]
    home_id = entry.data["home_id"]

    session = async_get_clientsession(hass)
    api = IntuisAPI(session, home_id)
    api._refresh_token = refresh_token
    try:
        await api.async_refresh_access_token()
    except InvalidAuth as err:
        raise ConfigEntryAuthFailed from err
    except CannotConnect as err:
        raise ConfigEntryNotReady from err

    # rooms mapping
    home_data = await api.async_get_homes_data()
    rooms = {r["id"]: r.get("name", f"Room {r['id']}") for r in home_data.get("rooms", [])}
    if not rooms:
        raise ConfigEntryNotReady("No rooms found")

    async def _async_update():
        try:
            raw = await api.async_get_home_status()
        except (CannotConnect, APIError) as err:
            raise UpdateFailed(str(err)) from err
        home = raw.get("body", {}).get("home", {})
        modules = home.get("modules", [])
        modules_by_room = {}
        for mod in modules:
            modules_by_room.setdefault(mod.get("room_id"), []).append(mod)
        data = {}
        for room in home.get("rooms", []):
            rid = room["id"]
            info = {
                "temperature": room.get("therm_measured_temperature"),
                "target_temperature": room.get("therm_setpoint_temperature"),
                "mode": room.get("therm_setpoint_mode"),
                "heating": False,
                "presence": False,
                "open_window": False,
                "power": 0,
            }
            for mod in modules_by_room.get(rid, []):
                if mod.get("heating_power_request", 0) > 0:
                    info["heating"] = True
                info["power"] = max(info["power"], mod.get("heating_power_request", 0))
                if mod.get("presence"):
                    info["presence"] = True
                if mod.get("open_window_detected"):
                    info["open_window"] = True
            data[rid] = info
        return data

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="intuis_connect",
        update_method=_async_update,
        update_interval=datetime.timedelta(minutes=5),
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
        "home_id": api.home_id,
        "rooms": rooms,
    }

    await hass.config_entries.async_forward_entry_setups(entry, ["climate", "binary_sensor", "sensor"])
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["climate", "binary_sensor", "sensor"])
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
