from typing import Any

from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.intuis_connect.data import IntuisRoom

IntuisDataUpdateCoordinator = DataUpdateCoordinator[dict[str, Any]]

class IntuisEntity(Entity):
    """Base class for Intuis entities."""

    def __init__(self, coordinator: IntuisDataUpdateCoordinator, room: IntuisRoom, home_id: str, name: str, entity_type: str) -> None:
        """Initialize the Intuis entity."""
        Entity.__init__(self)
        self._coordinator = coordinator
        self._room = room
        self._home_id = home_id
        self._attr_name = name
        self._attr_unique_id = f"{self._get_id_prefix()}_{entity_type}"

    def _get_room(self) -> IntuisRoom | None:
        """Get the room object by ID."""
        rooms = self._coordinator.data.get("rooms", {})
        return rooms.get(self._room.id)

    def _get_id_prefix(self):
        return f"intuis_{self._home_id}_{self._room.id}"