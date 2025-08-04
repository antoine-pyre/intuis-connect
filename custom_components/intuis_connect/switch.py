
"""Child-lock switch platform."""
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .device import build_device_info
from .const import DOMAIN

class ChildLockSwitch(CoordinatorEntity, SwitchEntity):
    def __init__(self, coordinator, api, home_id, room_id, room_name):
        super().__init__(coordinator)
        self._api = api
        self._room_id = room_id
        self._dev = build_device_info(home_id, room_id, room_name)
        self._attr_name = f"{room_name} Child Lock"
        self._attr_unique_id = f"{room_id}_child_lock"
    @property
    def device_info(self):
        return self._dev
    @property
    def is_on(self):
        return self.coordinator.data[self._room_id].get("child_lock", False)
    async def async_turn_on(self, **kwargs):
        await self._api.async_set_child_lock(self._room_id, True)
        await self.coordinator.async_request_refresh()
    async def async_turn_off(self, **kwargs):
        await self._api.async_set_child_lock(self._room_id, False)
        await self.coordinator.async_request_refresh()

async def async_setup_entry(hass, entry, async_add_entities):
    d = hass.data[DOMAIN][entry.entry_id]
    ents = [ChildLockSwitch(d["coordinator"], d["api"], d["home_id"], rid, name) for rid, name in d["rooms"].items()]
    async_add_entities(ents)
