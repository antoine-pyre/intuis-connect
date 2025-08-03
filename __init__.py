
"""Setup for Intuis Connect (v1.3.0)."""
from __future__ import annotations

import logging, datetime, asyncio
from collections import defaultdict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.service
from homeassistant.helpers import config_validation as cv
from homeassistant.const import CONF_PLATFORM
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from .const import DOMAIN
from .api import IntuisAPI, CannotConnect, InvalidAuth, APIError

CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["climate", "binary_sensor", "sensor", "switch"]

SERVICE_CLEAR_OVERRIDE = "clear_override"
ATTR_ROOM_ID = "room_id"

CLEAR_OVERRIDE_SCHEMA = vol.Schema({vol.Required(ATTR_ROOM_ID): str})

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Create API + coordinator, register platforms & services."""
    hass.data.setdefault(DOMAIN, {})
    session = async_get_clientsession(hass)
    api = IntuisAPI(session, home_id=entry.data["home_id"])
    api._refresh_token = entry.data["refresh_token"]

    try:
        await api.async_refresh_access_token()
    except InvalidAuth as err:
        raise ConfigEntryAuthFailed from err
    except CannotConnect as err:
        raise ConfigEntryNotReady from err

    home_data = await api.async_get_homes_data()
    rooms = {r["id"]: r.get("name", f"Room {r['id']}") for r in home_data.get("rooms", [])}
    if not rooms:
        raise ConfigEntryNotReady("No rooms returned")

    # State accumulators
    minutes_counter = defaultdict(int)
    energy_cache = {}

    async def _async_update():
        """Fetch status, annotate with heating minutes and energy."""
        try:
            raw = await api.async_get_home_status()
        except (CannotConnect, APIError) as err:
            raise UpdateFailed(str(err)) from err

        home = raw.get("body", {}).get("home", {})
        modules = home.get("modules", [])
        mods_by_room = defaultdict(list)
        for mod in modules:
            mods_by_room[mod.get("room_id")].append(mod)

        data_by_room = {}
        now = datetime.datetime.utcnow()
        today_iso = now.date().isoformat()
        for room in home.get("rooms", []):
            rid = room["id"]
            info = {
                "temperature": room.get("therm_measured_temperature"),
                "target_temperature": room.get("therm_setpoint_temperature"),
                "mode": room.get("therm_setpoint_mode"),
                "heating": False,
                "presence": False,
                "open_window": False,
                "anticipation": False,
                "power": 0,
            }
            for mod in mods_by_room.get(rid, []):
                if mod.get("heating_power_request", 0) > 0:
                    info["heating"] = True
                info["power"] = max(info["power"], mod.get("heating_power_request", 0))
                if mod.get("presence"):
                    info["presence"] = True
                if mod.get("open_window_detected"):
                    info["open_window"] = True
                if mod.get("anticipating"):
                    info["anticipation"] = True

            # Accumulate heating minutes
            if info["heating"]:
                minutes_counter[rid] += 5  # because update interval is 5 min
            # Reset at midnight UTC
            if now.hour == 0 and now.minute < 5:
                minutes_counter[rid] = 0
            info["minutes"] = minutes_counter[rid]

            # Get daily kWh once after 02:00
            cache_key = f"{rid}_{today_iso}"
            if cache_key not in energy_cache and now.hour >= 2:
                energy_cache[cache_key] = await api.async_get_home_measure(rid, today_iso)
            info["energy"] = energy_cache.get(cache_key, 0.0)

            data_by_room[rid] = info
        return data_by_room

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

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register service: clear_override
 
    @callback
    async def async_clear_override(call):
        """Cancel manual/boost and resume schedule for one room."""
        room_id = call.data[ATTR_ROOM_ID]
        api = hass.data[DOMAIN][entry.entry_id]["api"]
        await api.async_set_room_state(room_id, "home")
        await hass.data[DOMAIN][entry.entry_id]["coordinator"].async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAR_OVERRIDE,
        async_clear_override,
        schema=CLEAR_OVERRIDE_SCHEMA,
    )

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
