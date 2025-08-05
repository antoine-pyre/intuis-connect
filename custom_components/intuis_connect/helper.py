"""Helper functions for the Intuis Connect integration."""
from __future__ import annotations

import logging
from typing import Tuple

from aiohttp import ClientSession
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .api import IntuisAPI, CannotConnect, InvalidAuth
from .const import DOMAIN
from .entity.intuis_entity import IntuisDataUpdateCoordinator
from .intuis_data import IntuisRoom

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


def get_coordinator(hass, entry) -> IntuisDataUpdateCoordinator:
    """Get the Intuis data update coordinator from the Home Assistant instance."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]

    return coordinator


def get_home(coordinator: IntuisDataUpdateCoordinator) -> str:
    """Get the home ID from the coordinator data."""
    return coordinator.data.get("id", "unknown_home")


def get_rooms(coordinator: IntuisDataUpdateCoordinator) -> dict[str, IntuisRoom]:
    """Get the rooms data from the coordinator."""
    rooms = coordinator.data.get("rooms", {})
    if not rooms:
        _LOGGER.warning("No rooms found in coordinator data")
    return rooms


def get_room(coordinator: IntuisDataUpdateCoordinator, room_id: str) -> IntuisRoom | None:
    """Get the room data from the coordinator by room ID."""
    room = get_rooms(coordinator).get(room_id)
    if room:
        return room
    _LOGGER.warning("Room %s not found in coordinator data", room_id)
    return None


def get_api(hass: HomeAssistant, entry: ConfigEntry) -> IntuisAPI:
    """Get the Intuis API instance from the Home Assistant instance."""
    if DOMAIN not in hass.data or entry.entry_id not in hass.data[DOMAIN]:
        _LOGGER.error("No data found for entry %s", entry.entry_id)
        raise ValueError("No API instance found")
    data = hass.data[DOMAIN][entry.entry_id]
    api = data["api"]
    return api


def get_home_id(hass: HomeAssistant, entry: ConfigEntry) -> str:
    """Get the home ID from the config entry."""
    if DOMAIN not in hass.data or entry.entry_id not in hass.data[DOMAIN]:
        _LOGGER.error("No data found for entry %s", entry.entry_id)
        return "unknown_home"

    return get_api(hass, entry).home_id


def get_basic_utils(hass: HomeAssistant, entry: ConfigEntry) -> Tuple[
    IntuisDataUpdateCoordinator, str, dict[str, IntuisRoom], IntuisAPI]:
    """Get basic utilities from the Home Assistant instance."""
    coordinator = get_coordinator(hass, entry)
    home_id = get_home_id(hass, entry)
    rooms = get_rooms(coordinator)
    api = get_api(hass, entry)

    return coordinator, home_id, rooms, api
