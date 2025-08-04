from custom_components.intuis_connect import IntuisDataUpdateCoordinator
from custom_components.intuis_connect.data import IntuisRoom


class IntuisEntity:
    """Base class for Intuis entities."""

    def __init__(self, coordinator: IntuisDataUpdateCoordinator, room: IntuisRoom, home_id: str) -> None:
        self._coordinator = coordinator
        self._room = room
        self._home_id = home_id

    def _get_room(self) -> IntuisRoom | None:
        """Get the room object by ID."""
        rooms = self._coordinator.data.get("rooms", {})
        return rooms.get(self._room.id)