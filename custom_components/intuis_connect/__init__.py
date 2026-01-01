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
from .entity.intuis_schedule import IntuisSchedule, IntuisThermSchedule, IntuisThermZone
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
SERVICE_SET_SCHEDULE_SLOT = "set_schedule_slot"

# Service attributes
ATTR_ROOM_ID = "room_id"
ATTR_SCHEDULE_ID = "schedule_id"
ATTR_SCHEDULE_NAME = "schedule_name"
ATTR_DAY = "day"
ATTR_START_TIME = "start_time"
ATTR_ZONE_ID = "zone_id"
ATTR_ZONE_NAME = "zone_name"

# Service schemas
CLEAR_OVERRIDE_SCHEMA = vol.Schema({vol.Required(ATTR_ROOM_ID): str})
SWITCH_SCHEDULE_SCHEMA = vol.Schema({
    vol.Optional(ATTR_SCHEDULE_ID): str,
    vol.Optional(ATTR_SCHEDULE_NAME): str,
})
REFRESH_SCHEDULES_SCHEMA = vol.Schema({})
SET_SCHEDULE_SLOT_SCHEMA = vol.Schema({
    vol.Required(ATTR_DAY): vol.All(vol.Coerce(int), vol.Range(min=0, max=6)),
    vol.Required(ATTR_START_TIME): str,  # HH:MM format
    vol.Optional(ATTR_ZONE_ID): vol.Coerce(int),
    vol.Optional(ATTR_ZONE_NAME): str,
})

# Day constants for readability
DAYS_OF_WEEK = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MINUTES_PER_DAY = 1440


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

    async def async_handle_set_schedule_slot(call: ServiceCall) -> None:
        """Handle set_schedule_slot service call.

        Sets a zone for a specific time slot in the active schedule.
        """
        day = call.data.get(ATTR_DAY)
        start_time = call.data.get(ATTR_START_TIME)
        zone_id = call.data.get(ATTR_ZONE_ID)
        zone_name = call.data.get(ATTR_ZONE_NAME)

        if zone_id is None and zone_name is None:
            _LOGGER.error("Either zone_id or zone_name must be provided")
            return

        # Parse start_time (HH:MM format)
        try:
            hours, minutes = map(int, start_time.split(":"))
            if not (0 <= hours <= 23 and 0 <= minutes <= 59):
                raise ValueError("Invalid time")
        except (ValueError, AttributeError):
            _LOGGER.error("Invalid start_time format: %s (expected HH:MM)", start_time)
            return

        # Calculate m_offset (minutes from Monday 00:00)
        m_offset = day * MINUTES_PER_DAY + hours * 60 + minutes

        for entry_id, data in hass.data[DOMAIN].items():
            if not isinstance(data, dict):
                continue

            api: IntuisAPI = data.get("api")
            intuis_home: IntuisHome = data.get("intuis_home")
            coordinator = data.get("coordinator")

            if not api or not intuis_home:
                continue

            # Find the active therm schedule
            active_schedule = None
            for schedule in intuis_home.schedules:
                if isinstance(schedule, IntuisThermSchedule) and schedule.selected:
                    active_schedule = schedule
                    break

            if not active_schedule:
                _LOGGER.error("No active therm schedule found")
                return

            # Find the target zone
            target_zone = None
            for zone in active_schedule.zones:
                if isinstance(zone, IntuisThermZone):
                    if zone_id is not None and zone.id == zone_id:
                        target_zone = zone
                        break
                    if zone_name is not None and zone.name.lower() == zone_name.lower():
                        target_zone = zone
                        break

            if not target_zone:
                _LOGGER.error(
                    "Zone not found: id=%s, name=%s. Available zones: %s",
                    zone_id,
                    zone_name,
                    [(z.id, z.name) for z in active_schedule.zones if isinstance(z, IntuisThermZone)],
                )
                return

            _LOGGER.info(
                "Setting zone '%s' (ID: %d) at %s %s (m_offset: %d)",
                target_zone.name,
                target_zone.id,
                DAYS_OF_WEEK[day],
                start_time,
                m_offset,
            )

            # Build updated timetable
            # Find if there's an existing entry at this m_offset
            timetable = [
                {"zone_id": t.zone_id, "m_offset": t.m_offset}
                for t in active_schedule.timetables
            ]

            # Update or insert the entry
            entry_found = False
            for entry in timetable:
                if entry["m_offset"] == m_offset:
                    entry["zone_id"] = target_zone.id
                    entry_found = True
                    break

            if not entry_found:
                timetable.append({"zone_id": target_zone.id, "m_offset": m_offset})

            # Sort timetable by m_offset
            timetable.sort(key=lambda x: x["m_offset"])

            # Remove consecutive duplicate zones (API rejects these)
            cleaned_timetable = []
            prev_zone_id = None
            for entry in timetable:
                if entry["zone_id"] != prev_zone_id:
                    cleaned_timetable.append(entry)
                    prev_zone_id = entry["zone_id"]
                else:
                    _LOGGER.debug(
                        "Skipping duplicate zone_id %d at m_offset %d",
                        entry["zone_id"],
                        entry["m_offset"],
                    )
            timetable = cleaned_timetable

            # Build zones payload (only rooms_temp, not rooms - API requirement)
            zones_payload = []
            for zone in active_schedule.zones:
                if isinstance(zone, IntuisThermZone):
                    zone_data = {
                        "id": zone.id,
                        "name": zone.name,
                        "type": zone.type,
                        "rooms_temp": [
                            {"room_id": rt.room_id, "temp": rt.temp}
                            for rt in zone.rooms_temp
                        ],
                    }
                    zones_payload.append(zone_data)

            try:
                await api.async_sync_schedule(
                    schedule_id=active_schedule.id,
                    schedule_name=active_schedule.name,
                    schedule_type=active_schedule.type,
                    timetable=timetable,
                    zones=zones_payload,
                    away_temp=active_schedule.away_temp,
                    hg_temp=active_schedule.hg_temp,
                )

                # Update local timetable state
                from .entity.intuis_schedule import IntuisTimetable
                active_schedule.timetables = [
                    IntuisTimetable(zone_id=t["zone_id"], m_offset=t["m_offset"])
                    for t in timetable
                ]

                # Refresh coordinator
                if coordinator:
                    await coordinator.async_request_refresh()

                _LOGGER.info("Schedule slot updated successfully")

            except Exception as err:
                _LOGGER.error("Failed to set schedule slot: %s", err)
                raise

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

    if not hass.services.has_service(DOMAIN, SERVICE_SET_SCHEDULE_SLOT):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_SCHEDULE_SLOT,
            async_handle_set_schedule_slot,
            schema=SET_SCHEDULE_SLOT_SCHEMA,
        )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading entry %s", entry.entry_id)
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
        _LOGGER.debug("Unloaded entry %s", entry.entry_id)
    return unload_ok
