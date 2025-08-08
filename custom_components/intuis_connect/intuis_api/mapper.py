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
        mid = module["id"]
        modules.append(IntuisModule.from_dict(module))
        _LOGGER.debug("Module %s data: %s", mid, module)

    return modules


def extract_rooms(home: dict[str, Any],
                        modules: list[IntuisModule],
                        minutes_counter: dict[str, int],
                        rooms_definitions: dict[str, IntuisRoomDefinition],
                        last_update_timestamp: datetime | None,
                        ) -> dict[str, IntuisRoom]:
    """Extract rooms from the Intuis Connect system."""
    rooms_raw: list[dict[str, Any]] = home.get("rooms", [])

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

        if intuis_room.heating and last_update_timestamp is not None:
            delta = (now - last_update_timestamp).total_seconds() / 60.0
            delta = min(delta, DEFAULT_UPDATE_INTERVAL * 1.5)
            if delta > 0:
                minutes_counter[room_id] += delta

        intuis_room.minutes = minutes_counter[room_id]

        # ---- daily kWh ---
        # cache_key = f"{rid}_{today_iso}"
        # if cache_key not in energy_cache and now.hour >= 2:
        #     _LOGGER.debug("Fetching energy data for room %s on %s", rid, today_iso)
        #     energy_cache[cache_key] = await api.async_get_home_measure(
        #         rid, today_iso
        #     )
        # info.energy = energy_cache.get(cache_key, 0.0)
        _LOGGER.debug("Room %s data compiled: %s", room_id, intuis_room)

        data_by_room[room_id] = intuis_room

    return data_by_room
