"""Privacy-preserving support snapshot, inspired by adrienvsj's diagnostics.

Adapted-from: https://github.com/adrienvsj/intuis-connect/commit/acc734719c7e0484c949f89fc6d9a1a910c67252
Original-author: @adrienvsj
Only explicitly selected fields are exported; no raw entry, API response,
exception message, registry ID, room/schedule name or location is returned.
"""

from __future__ import annotations

from copy import deepcopy
import math
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .utils.const import DOMAIN


def _number(value):
    return value if type(value) in (int, float) and math.isfinite(value) else None


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return anonymous aliases shared across room state and last daily import."""
    domain = hass.data.get(DOMAIN, {})
    data = domain.get(entry.entry_id, {})
    home = data.get("intuis_home")
    coordinator = data.get("coordinator")
    rooms = ((coordinator.data if coordinator else None) or {}).get("rooms", {})
    manager = domain.get("import_managers", {}).get(entry.entry_id)
    reports = deepcopy(manager.daily_diagnostics) if manager else {}
    aliases = {
        room_id: f"room_{index}"
        for index, room_id in enumerate(dict.fromkeys([*rooms, *reports]), 1)
    }
    room_states = {}
    for room_id, room in rooms.items():
        mode = getattr(room, "mode", None)
        room_states[aliases[room_id]] = {
            "mode": mode if mode in {"manual", "home", "auto", "away", "hg", "off", "boost"} else "unknown",
            "temperature": _number(getattr(room, "temperature", None)),
            "target_temperature": _number(getattr(room, "target_temperature", None)),
            "energy_kwh": _number(getattr(room, "energy", None)),
            "module_count": len(getattr(room, "modules", None) or []),
        }
    return {
        "entry": {"version": entry.version},
        "home": {
            "room_count": len(getattr(home, "rooms", None) or {}),
            "schedules": [
                {
                    "selected": bool(schedule.selected),
                    "zone_count": len(getattr(schedule, "zones", None) or []),
                    "timetable_entries": len(getattr(schedule, "timetables", None) or []),
                }
                for schedule in getattr(home, "schedules", None) or []
            ],
        },
        "coordinator": {
            "last_update_success": bool(coordinator.last_update_success) if coordinator else None,
            "update_interval_seconds": coordinator.update_interval.total_seconds()
            if coordinator and coordinator.update_interval else None,
        },
        "rooms": room_states,
        "history_import": {
            "status": manager.status if manager else "not_started",
            "running": manager.is_running if manager else False,
            "last_daily_run": {aliases[key]: value for key, value in reports.items()},
        },
        "hourly_statistics": {"enabled": data.get("hourly_updater") is not None},
    }
