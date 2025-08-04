"""Setup for Intuis Connect (v1.3.0)."""
from __future__ import annotations

import datetime
import logging
from collections import defaultdict

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import IntuisAPI, CannotConnect, InvalidAuth, APIError
from .const import DOMAIN

CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)

_LOGGER = logging.getLogger(__name__)
_LOGGER.debug("Intuis Connect component initialized")

PLATFORMS = ["calendar", "climate", "binary_sensor", "sensor"]

SERVICE_CLEAR_OVERRIDE = "clear_override"
ATTR_ROOM_ID = "room_id"

CLEAR_OVERRIDE_SCHEMA = vol.Schema({vol.Required(ATTR_ROOM_ID): str})


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    _LOGGER.debug("async_setup")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Intuis Connect from a config entry."""
    _LOGGER.debug("Setting up entry %s", entry.entry_id)
    hass.data.setdefault(DOMAIN, {})

    session = async_get_clientsession(hass)
    api = IntuisAPI(session, home_id=entry.data["home_id"])
    api._refresh_token = entry.data["refresh_token"]

    try:
        _LOGGER.debug("Refreshing access token for entry %s", entry.entry_id)
        await api.async_refresh_access_token()
        _LOGGER.debug("Access token refreshed")
    except InvalidAuth as err:
        _LOGGER.error("Invalid authentication: %s", err)
        raise ConfigEntryAuthFailed from err
    except CannotConnect as err:
        _LOGGER.warning("Cannot connect to Intuis API: %s", err)
        raise ConfigEntryNotReady from err

    home_data = await api.async_get_homes_data()
    _LOGGER.debug("Retrieved homes data: %s", home_data)
    rooms = {r["id"]: r.get("name", f"Room {r['id']}") for r in home_data["rooms"]}

    # ---------- coordinator update -------------------------------------------------
    minutes_counter: dict[str, int] = defaultdict(int)
    energy_cache: dict[str, float] = {}

    async def _async_update():
        _LOGGER.debug("Coordinator update started")
        try:
            status = await api.async_get_home_status()
        except (CannotConnect, APIError) as err:
            _LOGGER.error("Error fetching home status: %s", err)
            raise UpdateFailed(str(err)) from err

        home = status["body"]["home"]
        _LOGGER.debug("Home status received: %s", home)
        modules_raw = home.get("modules", [])
        rooms_raw = home.get("rooms", [])

        # ---- build module dict ----------------------------------------------------
        modules: dict[str, dict] = {}
        for mod in modules_raw:
            mid = mod["id"]
            modules[mid] = {
                "room_id": mod.get("room_id"),
                "room_name": rooms.get(mod.get("room_id"), "Unknown"),
                "keypad_locked": bool(mod.get("keypad_locked")),
            }
        _LOGGER.debug("Built module information for %d modules", len(modules))

        # ---- build room dict ------------------------------------------------------
        data_by_room: dict[str, dict] = {}
        now = datetime.datetime.utcnow()
        today_iso = now.date().isoformat()

        for room in rooms_raw:
            rid = room["id"]
            info = {
                "temperature": room.get("therm_measured_temperature"),
                "target_temperature": room.get("therm_setpoint_temperature"),
                "mode": room.get("therm_setpoint_mode"),
                "heating": any(
                    m.get("heating_power_request", 0) > 0
                    for m in modules_raw
                    if m.get("room_id") == rid
                ),
                "presence": any(
                    m.get("presence") for m in modules_raw if m.get("room_id") == rid
                ),
                "open_window": any(
                    m.get("open_window_detected")
                    for m in modules_raw
                    if m.get("room_id") == rid
                ),
                "anticipation": any(
                    m.get("anticipating") for m in modules_raw if m.get("room_id") == rid
                ),
                "power": max(
                    (m.get("heating_power_request", 0)
                     for m in modules_raw if m.get("room_id") == rid),
                    default=0,
                ),
            }

            # ---- heating-minutes counter ------------------------------------------
            if info["heating"]:
                minutes_counter[rid] += 5
            if now.hour == 0 and now.minute < 5:
                minutes_counter[rid] = 0
            info["minutes"] = minutes_counter[rid]

            # ---- daily kWh ---------------------------------------------------------
            cache_key = f"{rid}_{today_iso}"
            if cache_key not in energy_cache and now.hour >= 2:
                _LOGGER.debug("Fetching energy data for room %s on %s", rid, today_iso)
                energy_cache[cache_key] = await api.async_get_home_measure(
                    rid, today_iso
                )
            info["energy"] = energy_cache.get(cache_key, 0.0)
            _LOGGER.debug("Room %s data compiled: %s", rid, info)

            data_by_room[rid] = info

        # ─── pull the active schedule ───────────────────────────
        schedule = {}
        active_id = home.get("active_schedule_id")
        if active_id:
            schedule = await api.async_get_schedule(api.home_id, active_id)
        _LOGGER.debug("Active schedule for home %s: %s", api.home_id, schedule)

        # return both rooms and modules
        _LOGGER.debug("Coordinator update completed")
        return {
            "rooms": data_by_room,
            "modules": modules,
            "schedule": schedule,
        }

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="intuis_connect",
        update_method=_async_update,
        update_interval=datetime.timedelta(minutes=5),
    )
    await coordinator.async_config_entry_first_refresh()

    # ---------- store everything ---------------------------------------------------
    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
        "home_id": api.home_id,
        "rooms": rooms,
        "modules": coordinator.data["modules"],
        "schedule": coordinator.data["schedule"],
    }
    _LOGGER.debug("Stored data for entry %s", entry.entry_id)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # ---------- clear-override service --------------------------------------------
    @callback
    async def async_clear_override(call):
        _LOGGER.debug("Clearing override for room %s", call.data[ATTR_ROOM_ID])
        room_id = call.data[ATTR_ROOM_ID]
        await api.async_set_room_state(room_id, "home")
        await coordinator.async_request_refresh()
        _LOGGER.debug("Override cleared for room %s", room_id)

    hass.services.async_register(
        DOMAIN, SERVICE_CLEAR_OVERRIDE, async_clear_override, schema=CLEAR_OVERRIDE_SCHEMA
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _LOGGER.debug("Unloading entry %s", entry.entry_id)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        _LOGGER.debug("Unloaded entry %s", entry.entry_id)
    return unload_ok
