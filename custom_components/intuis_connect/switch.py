"""Child-lock switch platform."""
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .device import build_device_info
from .const import DOMAIN

class ChildLockSwitch(CoordinatorEntity, SwitchEntity):
    def __init__(self, coordinator, api, module_id: str, room_name: str):
        super().__init__(coordinator)
        self._api = api
        self._module_id = module_id
        self._attr_name = f"{room_name} Child Lock"
        self._attr_unique_id = f"{module_id}_child_lock"
        self._dev = build_device_info(coordinator.data["rooms"][ api.home_id ], module_id, room_name)

    @property
    def device_info(self):
        return self._dev

    @property
    def is_on(self) -> bool:
        # read the latest keypad_locked state from the coordinator
        return bool(self.coordinator.data["modules"][self._module_id].get("keypad_locked", False))

    async def async_turn_on(self, **kwargs) -> None:
        await self._api.async_set_child_lock(self._module_id, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self._api.async_set_child_lock(self._module_id, False)
        await self.coordinator.async_request_refresh()


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up ChildLockSwitch entities from config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    api = data["api"]

    # Grab the modules dict from the coordinator
    modules = coordinator.data.get("modules", {})

    # Create one switch per module
    switches = [
        ChildLockSwitch(coordinator, api, module_id, module_info["room_name"])
        for module_id, module_info in modules.items()
    ]
    async_add_entities(switches)
