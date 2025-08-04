
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

    @property
    def is_on(self) -> bool:
        return self.coordinator.data["modules"][self._module_id]["keypad_locked"]

    async def async_turn_on(self, **_):
        await self._api.async_set_child_lock(self._module_id, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **_):
        await self._api.async_set_child_lock(self._module_id, False)
        await self.coordinator.async_request_refresh()


async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    entities = [
        ChildLockSwitch(data["coordinator"], data["api"], mod_id, mod["room_name"])
        for mod_id, mod in data["modules"].items()
    ]
    async_add_entities(entities)