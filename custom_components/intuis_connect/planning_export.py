"""Export the loaded planning model without credentials or cloud identifiers."""

from __future__ import annotations

from typing import Any

from .entity.intuis_schedule import (
    IntuisElectricitySchedule,
    IntuisElectricityZone,
    IntuisEventZone,
    IntuisThermSchedule,
    IntuisThermZone,
)


def export_plannings(home: Any, room_aliases: dict[str, str]) -> dict[str, Any]:
    """Copy every loaded schedule, including inactive schedules and unused zones.

    Names are intentionally retained for migration. Account, home, schedule,
    room and module cloud identifiers are never copied. Both thermostat room
    representations are kept separately to avoid losing pilot-wire settings.
    This is a model export, not a raw cloud backup or an automatic HA import.
    """
    schedules = [s for s in getattr(home, "schedules", None) or [] if s is not None]
    room_definitions = getattr(home, "rooms", None) or {}
    aliases = dict(room_aliases)
    for room_id in room_definitions:
        aliases.setdefault(room_id, f"room_{len(aliases) + 1}")
    for schedule in schedules:
        for zone in getattr(schedule, "zones", None) or []:
            if isinstance(zone, IntuisThermZone):
                for room in zone.rooms_temp:
                    aliases.setdefault(room.room_id, f"room_{len(aliases) + 1}")
                for room in zone.rooms:
                    aliases.setdefault(room.id, f"room_{len(aliases) + 1}")

    module_aliases: dict[str, str] = {}
    exported = []
    for index, schedule in enumerate(schedules, 1):
        item = {
            "id": f"schedule_{index}",
            "name": getattr(schedule, "name", None),
            "type": getattr(schedule, "type", None),
            "default": bool(getattr(schedule, "default", False)),
            "selected": bool(getattr(schedule, "selected", False)),
            "timetable": [
                {"m_offset": t.m_offset, "zone_id": t.zone_id}
                for t in getattr(schedule, "timetables", None) or []
                if hasattr(t, "m_offset") and hasattr(t, "zone_id")
            ],
            "zones": [],
        }
        for zone in getattr(schedule, "zones", None) or []:
            if isinstance(zone, IntuisThermZone):
                item["zones"].append({
                    "id": zone.id,
                    "name": zone.name,
                    "type": zone.type,
                    "rooms_temp": [
                        {"room_id": aliases[r.room_id], "temp": r.temp}
                        for r in zone.rooms_temp
                    ],
                    "rooms": [
                        {
                            "id": aliases[r.id],
                            "therm_setpoint_temperature": r.therm_setpoint_temperature,
                            "therm_setpoint_fp": r.therm_setpoint_fp,
                        }
                        for r in zone.rooms
                    ],
                })
            elif isinstance(zone, IntuisElectricityZone):
                item["zones"].append({
                    "id": zone.id, "price_type": zone.price_type, "price": zone.price,
                })
            elif isinstance(zone, IntuisEventZone):
                modules = []
                for module in zone.modules:
                    if not isinstance(module, dict) or module.get("id") is None:
                        continue
                    module_id = module["id"]
                    module_aliases.setdefault(module_id, f"module_{len(module_aliases) + 1}")
                    modules.append({
                        "id": module_aliases[module_id],
                        "dhw_state": module.get("dhw_state"),
                    })
                item["zones"].append({"id": zone.id, "name": zone.name, "modules": modules})
        if isinstance(schedule, IntuisThermSchedule):
            item.update(away_temp=schedule.away_temp, hg_temp=schedule.hg_temp)
        elif isinstance(schedule, IntuisElectricitySchedule):
            item.update({
                key: getattr(schedule, key)
                for key in (
                    "tariff", "tariff_option", "power_threshold",
                    "contract_power_unit", "version",
                )
            })
        exported.append(item)

    return {
        "schema_version": 1,
        "source": "loaded_model",
        "timezone": getattr(home, "timezone", None),
        "week_start": "Monday",
        "timetable_unit": "minutes_from_week_start",
        "rooms": [
            {"id": alias, "name": getattr(room_definitions.get(room_id), "name", None)}
            for room_id, alias in aliases.items()
        ],
        "schedules": exported,
    }
