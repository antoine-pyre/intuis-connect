"""Child-lock switch platform."""
import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .device import build_device_info
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

class ChildLockSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to lock/unlock the radiator keypad (child lock)."""

    def __init__(self, coordinator, api, home_id: str, module_id: str, room_name: str):
        super().__init__(coordinator)
        self._api = api
        self._home_id = home_id
        self._module_id = module_id
        self._attr_name = f"{room_name} Child Lock"
        # Unique per module
        self._attr_unique_id = f"{module_id}_child_lock"
        # Device grouping: use the room that this module belongs to
        room_id = coordinator.data["modules"][module_id]["room_id"]
        self._attr_device_info = build_device_info(home_id, room_id, room_name)

    @property
    def device_info(self):
        return self._attr_device_info

    @property
    def is_on(self) -> bool:
        """Return True if child lock is enabled."""
        locked = self.coordinator.data["modules"][self._module_id].get("keypad_locked", False)
        _LOGGER.debug("ChildLockSwitch %s is_on: %s", self._module_id, locked)
        return bool(locked)

    async def async_turn_on(self, **kwargs) -> None:
        """Enable child lock."""
        _LOGGER.debug("Setting child lock ON for %s", self._module_id)
        await self._api.async_set_child_lock(self._module_id, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        """Disable child lock."""
        _LOGGER.debug("Setting child lock OFF for %s", self._module_id)
        await self._api.async_set_child_lock(self._module_id, False)
        await self.coordinator.async_request_refresh()


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up ChildLockSwitch entities from config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    api = data["api"]
    home_id = data["home_id"]

    modules = coordinator.data.get("modules", {})
    _LOGGER.debug("Switch platform modules: %s", list(modules.keys()))

    switches = []
    for module_id, module_info in modules.items():
        room_name = module_info.get("room_name", "Unknown")
        switches.append(
            ChildLockSwitch(
                coordinator,
                api,
                home_id,
                module_id,
                room_name,
            )
        )
    async_add_entities(switches, update_before_add=False)
