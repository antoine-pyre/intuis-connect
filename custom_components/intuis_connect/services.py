"""Domain services with static schemas and validation against current home data."""

from __future__ import annotations

import logging
import json

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

from .entity.intuis_home import IntuisHome
from .entity.intuis_schedule import IntuisThermSchedule
from .history_import import (
    async_get_import_manager,
    DEFAULT_HISTORY_DAYS,
    MAX_HISTORY_DAYS,
)
from .schedule_mutations import async_set_schedule_slot, async_set_zone_temperature, async_sync_schedule
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
SERVICE_SYNC_SCHEDULE = "sync_schedule"
SERVICES = (
    SERVICE_SWITCH_SCHEDULE,
    SERVICE_REFRESH_SCHEDULES,
    SERVICE_SET_SCHEDULE_SLOT,
    SERVICE_SET_ZONE_TEMPERATURE,
    SERVICE_IMPORT_ENERGY_HISTORY,
    SERVICE_SYNC_SCHEDULE,
)

ATTR_ROOM_ID = "room_id"
ATTR_SCHEDULE_NAME = "schedule_name"
ATTR_SCHEDULE_ID = "schedule_id"
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
        vol.Optional(ATTR_SCHEDULE_NAME): _nonempty_name,
        vol.Optional(ATTR_SCHEDULE_ID): _nonempty_name,
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


def _timetable_payload(value):
    """Accept structured transitions or the original planning JSON representation."""
    if isinstance(value, str):
        if len(value) > 65536:
            raise vol.Invalid("Timetable payload too large")
        try:
            value = json.loads(value)
        except (ValueError, TypeError) as err:
            raise vol.Invalid("Invalid timetable JSON") from err
    if not isinstance(value, list) or not 1 <= len(value) <= 512:
        raise vol.Invalid("Timetable must contain 1 to 512 transitions")
    result, offsets = [], set()
    for row in value:
        if not isinstance(row, dict) or set(row) != {"m_offset", "zone_id"}:
            raise vol.Invalid("Transitions require only m_offset and zone_id")
        offset, zone = row["m_offset"], row["zone_id"]
        if (type(offset) is not int or not 0 <= offset < 10080
                or offset in offsets or type(zone) is not int):
            raise vol.Invalid("Invalid or duplicate timetable offset/zone")
        offsets.add(offset)
        result.append({"m_offset": offset, "zone_id": zone})
    return sorted(result, key=lambda row: row["m_offset"])


def _planning_temperature(maximum):
    def validate(value):
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not 5 <= value <= maximum or not float(value * 2).is_integer()):
            raise vol.Invalid("Planning temperatures require half degrees in range")
        return float(value)
    return validate


def _has_changes(value):
    if not any(key in value for key in ("timetable", "away_temp", "hg_temp")):
        raise vol.Invalid("At least one timetable or temperature change is required")
    return value


class PlanningSchema(vol.Schema):
    def __call__(self, data):
        return _has_changes(super().__call__(data))


SYNC_SCHEDULE_SCHEMA = PlanningSchema({
    **HOME_FIELD,
    vol.Optional(ATTR_SCHEDULE_ID): _nonempty_name,
    vol.Optional(ATTR_SCHEDULE_NAME): _nonempty_name,
    vol.Optional("timetable"): _timetable_payload,
    vol.Optional("away_temp"): _planning_temperature(25),
    vol.Optional("hg_temp"): _planning_temperature(15),
})


def _schedule_by_name(home: IntuisHome, name: str) -> IntuisThermSchedule:
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


def resolve_schedule(home: IntuisHome, schedule_id=None, schedule_name=None):
    """Resolve optional IDs/names within one home; omission retains active default."""
    candidates = [s for s in home.schedules if isinstance(s, IntuisThermSchedule)]
    if schedule_id is None and schedule_name is None:
        candidates = [s for s in candidates if s.selected]
    else:
        candidates = [s for s in candidates
                      if (schedule_id is None or s.id == schedule_id)
                      and (schedule_name is None or s.name == schedule_name)]
    if len(candidates) != 1:
        raise ServiceValidationError("Schedule target is unknown, ambiguous or inconsistent")
    return candidates[0]


def _room_by_name(home: IntuisHome, name: str) -> str:
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
        schedule = resolve_schedule(
            data["intuis_home"], call.data.get(ATTR_SCHEDULE_ID),
            call.data.get(ATTR_SCHEDULE_NAME),
        )
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

    async def sync_schedule(call: ServiceCall) -> None:
        entry_id, data = first_target(hass, call.data.get(ATTR_HOME_ID))
        schedule = resolve_schedule(data["intuis_home"], call.data.get(ATTR_SCHEDULE_ID),
                                    call.data.get(ATTR_SCHEDULE_NAME))
        try:
            await async_sync_schedule(data["api"], lambda: data["intuis_home"], schedule.id,
                                      **{key: call.data[key] for key in
                                         ("timetable", "away_temp", "hg_temp") if key in call.data})
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
        SERVICE_SYNC_SCHEDULE: (sync_schedule, SYNC_SCHEDULE_SCHEMA),
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
