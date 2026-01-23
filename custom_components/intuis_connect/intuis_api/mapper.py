import logging
from datetime import datetime
from typing import Any, List

from ..entity.intuis_module import IntuisModule
from ..entity.intuis_room import IntuisRoom, IntuisRoomDefinition
from ..utils.const import DEFAULT_UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)

def extract_modules(home: dict[str, Any]) -> List[IntuisModule]:
    modules_raw: list[dict[str, Any]] = home.get("modules", [])
    # --- process modules ---
    modules: List[IntuisModule] = []
    for module in modules_raw:
        mid = module.get("id", "unknown")
        try:
            modules.append(IntuisModule.from_dict(module))
            _LOGGER.debug("Module %s data: %s", mid, module)
        except (ValueError, KeyError, TypeError) as err:
            _LOGGER.warning("Skipping malformed module %s: %s", mid, err)

    return modules


def extract_rooms(home: dict[str, Any],
                        modules: list[IntuisModule],
                        minutes_counter: dict[str, int],
                        rooms_definitions: dict[str, IntuisRoomDefinition],
                        last_update_timestamp: datetime | None,
                        now: datetime | None = None,
                        ) -> dict[str, IntuisRoom]:
    """Extract rooms from the Intuis Connect system."""
    rooms_raw: list[dict[str, Any]] = home.get("rooms", [])

    if now is None:
        now = datetime.now()

    # --- process rooms ---
    data_by_room: dict[str, IntuisRoom] = {}
    for room in rooms_raw:
        room_id = room["id"]
        intuis_room: IntuisRoom = IntuisRoom.from_dict(
            rooms_definitions.get(room_id),
            room,
            modules
        )

        # ---- heating-minutes counter ---
        if room_id not in minutes_counter:
            minutes_counter[room_id] = 0

        if intuis_room.heating:
            if last_update_timestamp is not None:
                delta = (now - last_update_timestamp).total_seconds() / 60.0
                delta = min(delta, DEFAULT_UPDATE_INTERVAL * 1.5)
                if delta > 0:
                    minutes_counter[room_id] += delta
                    _LOGGER.debug(
                        "Room %s heating: added %.2f minutes (total: %.2f)",
                        room_id, delta, minutes_counter[room_id]
                    )
                else:
                    _LOGGER.debug(
                        "Room %s heating but delta <= 0 (%.2f), skipping increment",
                        room_id, delta
                    )
            else:
                _LOGGER.debug(
                    "Room %s is heating but last_update_timestamp is None (first update), skipping increment",
                    room_id
                )
        else:
            _LOGGER.debug(
                "Room %s not heating (heating=%s), minutes counter: %.2f",
                room_id, intuis_room.heating, minutes_counter[room_id]
            )

        intuis_room.minutes = int(minutes_counter[room_id])

        _LOGGER.debug("Room %s data compiled: %s", room_id, intuis_room)

        data_by_room[room_id] = intuis_room

    return data_by_room
