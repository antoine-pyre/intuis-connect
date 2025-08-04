"""Helper functions for the Intuis Connect integration."""
from __future__ import annotations

import logging
from typing import Any, Tuple

from aiohttp import ClientSession

from . import IntuisDataUpdateCoordinator
from .api import IntuisAPI, CannotConnect, InvalidAuth

_LOGGER = logging.getLogger(__name__)


async def async_validate_api(
    username: str, password: str, session: ClientSession
) -> Tuple[str, IntuisAPI]:
    """Validate the API and return the home ID and API instance."""
    api = IntuisAPI(session)
    try:
        home_id = await api.async_login(username, password)
        return home_id, api
    except (CannotConnect, InvalidAuth) as e:
        _LOGGER.error("API validation failed: %s", e)
        raise
    except Exception as e:
        _LOGGER.exception("Unknown error during API validation")
        raise InvalidAuth("unknown") from e


def get_home(coordinator: IntuisDataUpdateCoordinator) -> str:
    """Get the home ID from the coordinator data."""
    return coordinator.data.get("id", "unknown_home")


def get_room(coordinator: IntuisDataUpdateCoordinator, room_id: str) -> dict[str, Any] | None:
    """Get the room data from the coordinator by room ID."""
    room = coordinator.data["rooms"].get(room_id)
    if room:
        return room
    _LOGGER.warning("Room %s not found in coordinator data", room_id)
    return None


def get_room_name(coordinator: IntuisDataUpdateCoordinator, room_id: str) -> str | None:
    """Get the name of a room by its ID."""
    room = coordinator.data.get("rooms", {}).get(room_id)
    if room and "name" in room:
        return room["name"]
    _LOGGER.warning("Room %s not found", room_id)
    return None
