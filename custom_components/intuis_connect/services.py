"""Domain services with static schemas and validation against current home data."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TimeSelector,
    TimeSelectorConfig,
)

from .entity.intuis_schedule import IntuisThermSchedule
from .history_import import (
    async_get_import_manager,
    DEFAULT_HISTORY_DAYS,
    MAX_HISTORY_DAYS,
)
from .schedule_mutations import async_set_schedule_slot, async_set_zone_temperature
from .service_targets import first_target, is_loaded, require_targets, target_entries
from .timetable import schedule_slot_offsets
from .utils.const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SERVICE_CLEAR_OVERRIDE = "clear_override"
SERVICE_SWITCH_SCHEDULE = "switch_schedule"
SERVICE_REFRESH_SCHEDULES = "refresh_schedules"
SERVICE_SET_SCHEDULE_SLOT = "set_schedule_slot"
SERVICE_SET_ZONE_TEMPERATURE = "set_zone_temperature"
SERVICE_IMPORT_ENERGY_HISTORY = "import_energy_history"
SERVICES = (
    SERVICE_SWITCH_SCHEDULE,
    SERVICE_REFRESH_SCHEDULES,
    SERVICE_SET_SCHEDULE_SLOT,
    SERVICE_SET_ZONE_TEMPERATURE,
    SERVICE_IMPORT_ENERGY_HISTORY,
)

ATTR_ROOM_ID = "room_id"
ATTR_SCHEDULE_NAME = "schedule_name"
ATTR_HOME_ID = "home_id"
ATTR_DAY = "day"
ATTR_START_DAY = "start_day"
ATTR_END_DAY = "end_day"
ATTR_START_TIME = "start_time"
ATTR_END_TIME = "end_time"
ATTR_ZONE_NAME = "zone_name"
ATTR_ROOM_NAME = "room_name"
ATTR_TEMPERATURE = "temperature"
ATTR_DAYS = "days"


def _nonempty_name(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise vol.Invalid("A nonempty name or identifier is required")
    return value


def _history_days(value: float) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not 1 <= value <= MAX_HISTORY_DAYS
        or int(value) != value
    ):
        raise vol.Invalid(f"Days must be an integer from 1 to {MAX_HISTORY_DAYS}")
    return int(value)


HOME_FIELD = {vol.Optional(ATTR_HOME_ID): _nonempty_name}
CLEAR_OVERRIDE_SCHEMA = vol.Schema({vol.Required(ATTR_ROOM_ID): str})
REFRESH_SCHEDULES_SCHEMA = vol.Schema(HOME_FIELD)
SWITCH_SCHEDULE_SCHEMA = vol.Schema(
    {
        **HOME_FIELD,
        vol.Required(ATTR_SCHEDULE_NAME): _nonempty_name,
    }
)
SET_SCHEDULE_SLOT_SCHEMA = vol.Schema(
    {
        **HOME_FIELD,
        vol.Optional(ATTR_DAY): vol.Any(str, int),
        vol.Optional(ATTR_START_DAY): vol.Any(str, int),
        vol.Optional(ATTR_END_DAY): vol.Any(str, int),
        vol.Required(ATTR_START_TIME): TimeSelector(TimeSelectorConfig()),
        vol.Required(ATTR_END_TIME): TimeSelector(TimeSelectorConfig()),
        vol.Required(ATTR_ZONE_NAME): _nonempty_name,
    }
)
SET_ZONE_TEMPERATURE_SCHEMA = vol.Schema(
    {
        **HOME_FIELD,
        vol.Required(ATTR_SCHEDULE_NAME): _nonempty_name,
        vol.Required(ATTR_ZONE_NAME): _nonempty_name,
        vol.Required(ATTR_ROOM_NAME): _nonempty_name,
        vol.Required(ATTR_TEMPERATURE): NumberSelector(
            NumberSelectorConfig(
                min=5,
                max=30,
                step=0.5,
                unit_of_measurement="°C",
                mode=NumberSelectorMode.BOX,
            )
        ),
    }
)
IMPORT_ENERGY_HISTORY_SCHEMA = vol.Schema(
    {
        **HOME_FIELD,
        vol.Optional(ATTR_DAYS, default=DEFAULT_HISTORY_DAYS): _history_days,
        vol.Optional(ATTR_ROOM_NAME): str,
    }
)


def _schedule_by_name(home, name: str) -> IntuisThermSchedule:
    schedule = next(
        (
            s
            for s in home.schedules
            if isinstance(s, IntuisThermSchedule) and s.name == name
        ),
        None,
    )
    if schedule is None:
        raise ServiceValidationError(f"Schedule {name} not found in home {home.id}")
    return schedule


def _room_by_name(home, name: str) -> str:
    room_id = next(
        (
            rid
            for rid, room in home.rooms.items()
            if room.name.casefold() == name.casefold()
        ),
        None,
    )
    if room_id is None:
        raise ServiceValidationError(f"Room {name} not found in home {home.id}")
    return room_id


async def async_register_services(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register once per domain; handlers resolve homes on every invocation.

    The entry parameter remains for existing setup callers, but is not captured
    in any handler or schema. Adding or reloading an entry needs no schema rebuild.
    """

    async def switch_schedule(call: ServiceCall) -> None:
        entry_id, data = first_target(hass, call.data.get(ATTR_HOME_ID))
        home = data["intuis_home"]
        schedule = _schedule_by_name(home, call.data[ATTR_SCHEDULE_NAME])
        await data["api"].async_switch_schedule(home.id, schedule.id)
        if not is_loaded(hass, entry_id, data):
            return
        for current in data["intuis_home"].schedules:
            if isinstance(current, IntuisThermSchedule):
                current.selected = current.id == schedule.id
        if coordinator := data.get("coordinator"):
            await coordinator.async_request_refresh()

    async def refresh_schedules(call: ServiceCall) -> None:
        entries = require_targets(hass, call.data.get(ATTR_HOME_ID))
        for entry_id, data in entries:
            if not is_loaded(hass, entry_id, data):
                continue
            fresh_home = await data["api"].async_get_homes_data()
            if not is_loaded(hass, entry_id, data):
                continue
            data["intuis_home"].schedules = fresh_home.schedules
            data["intuis_home"].rooms = fresh_home.rooms
            if coordinator := data.get("coordinator"):
                await coordinator.async_request_refresh()

    async def set_schedule_slot(call: ServiceCall) -> None:
        entry_id, data = first_target(hass, call.data.get(ATTR_HOME_ID))
        schedule = next(
            (
                s
                for s in data["intuis_home"].schedules
                if isinstance(s, IntuisThermSchedule) and s.selected
            ),
            None,
        )
        if schedule is None:
            raise ServiceValidationError("No active heating schedule found")
        try:
            start, end = schedule_slot_offsets(
                call.data.get(ATTR_START_DAY, call.data.get(ATTR_DAY)),
                call.data[ATTR_START_TIME],
                call.data.get(ATTR_END_DAY, call.data.get(ATTR_DAY)),
                call.data[ATTR_END_TIME],
            )
            await async_set_schedule_slot(
                data["api"],
                lambda: data["intuis_home"],
                schedule.id,
                call.data[ATTR_ZONE_NAME],
                start,
                end,
            )
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        if is_loaded(hass, entry_id, data) and (coordinator := data.get("coordinator")):
            await coordinator.async_request_refresh()

    async def set_zone_temperature(call: ServiceCall) -> None:
        entry_id, data = first_target(hass, call.data.get(ATTR_HOME_ID))
        home = data["intuis_home"]
        schedule = _schedule_by_name(home, call.data[ATTR_SCHEDULE_NAME])
        room_id = _room_by_name(home, call.data[ATTR_ROOM_NAME])
        try:
            await async_set_zone_temperature(
                data["api"],
                lambda: data["intuis_home"],
                schedule.id,
                room_id,
                call.data[ATTR_TEMPERATURE],
                zone_name=call.data[ATTR_ZONE_NAME],
            )
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        if is_loaded(hass, entry_id, data) and (coordinator := data.get("coordinator")):
            await coordinator.async_request_refresh()

    async def import_energy_history(call: ServiceCall) -> None:
        entries = require_targets(hass, call.data.get(ATTR_HOME_ID))
        room_name = call.data.get(ATTR_ROOM_NAME) or None
        if room_name is not None and not room_name.strip():
            room_name = None
        if room_name:
            # With an explicit home, reject a bad room before creating any task.
            # Without one, the optional room name filters all loaded homes.
            if call.data.get(ATTR_HOME_ID) is not None:
                _room_by_name(entries[0][1]["intuis_home"], room_name)
            entries = [
                (eid, data)
                for eid, data in entries
                if any(
                    room.name.casefold() == room_name.casefold()
                    for room in data["intuis_home"].rooms.values()
                )
            ]
            if not entries:
                raise ServiceValidationError(
                    f"Room {room_name} not found in any loaded home"
                )
        for entry_id, data in entries:
            if not is_loaded(hass, entry_id, data):
                continue
            manager = await async_get_import_manager(hass, entry_id)
            if not is_loaded(hass, entry_id, data):
                continue
            if not manager.start(
                data["api"],
                data["intuis_home"],
                days=call.data[ATTR_DAYS],
                room_filter=room_name,
                home_id=data["intuis_home"].id,
            ):
                _LOGGER.warning(
                    "Energy history import already running or home unloading: %s",
                    data["intuis_home"].id,
                )

    handlers = {
        SERVICE_SWITCH_SCHEDULE: (switch_schedule, SWITCH_SCHEDULE_SCHEMA),
        SERVICE_REFRESH_SCHEDULES: (refresh_schedules, REFRESH_SCHEDULES_SCHEMA),
        SERVICE_SET_SCHEDULE_SLOT: (set_schedule_slot, SET_SCHEDULE_SLOT_SCHEMA),
        SERVICE_SET_ZONE_TEMPERATURE: (
            set_zone_temperature,
            SET_ZONE_TEMPERATURE_SCHEMA,
        ),
        SERVICE_IMPORT_ENERGY_HISTORY: (
            import_energy_history,
            IMPORT_ENERGY_HISTORY_SCHEMA,
        ),
    }
    for service, (handler, schema) in handlers.items():
        if not hass.services.has_service(DOMAIN, service):
            hass.services.async_register(DOMAIN, service, handler, schema=schema)


def async_unregister_services_if_unused(hass: HomeAssistant) -> None:
    """Keep domain services until the final loaded entry has been removed."""
    if not target_entries(hass):
        for service in SERVICES:
            hass.services.async_remove(DOMAIN, service)
