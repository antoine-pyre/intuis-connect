"""Helper functions for the Intuis Connect integration."""
import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)


def get_home(coordinator) -> str:
    """Get the home ID from the coordinator data."""
    return coordinator.data.get("id", "unknown_home")


def get_room(coordinator, room_id) -> Any | None:
    """Get the room data from the coordinator by room ID."""
    room = coordinator.data["rooms"][room_id]
    if room:
        return room
    _LOGGER.warning("Room %s not found in coordinator data", room_id)
    return None


def get_room_name(coordinator, room_id: str) -> Any | None:
    """Get the name of a room by its ID."""
    room = coordinator.data.get("rooms", {}).get(room_id)
    if room and "name" in room:
        return room["name"]
    _LOGGER.warning("Room %s not found", room_id)
    return None
