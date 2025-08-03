"""Binary sensors for Intuis Connect."""
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .device import build_device_info
from .const import DOMAIN

class IntuisPresenceSensor(CoordinatorEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.MOTION
    def __init__(self, coordinator, home_id, room_id, room_name):
        super().__init__(coordinator)
        self._room_id = room_id
        self._dev = build_device_info(home_id, room_id, room_name)
        self._attr_name = f"{room_name} Presence"
        self._attr_unique_id = f"{room_id}_presence"
    @property
    def is_on(self):
        return bool(self.coordinator.data.get(self._room_id, {}).get("presence"))
    @property
    def device_info(self):
        return self._dev

class IntuisWindowSensor(CoordinatorEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.WINDOW
    def __init__(self, coordinator, home_id, room_id, room_name):
        super().__init__(coordinator)
        self._room_id = room_id
        self._dev = build_device_info(home_id, room_id, room_name)
        self._attr_name = f"{room_name} Open Window"
        self._attr_unique_id = f"{room_id}_window"
    @property
    def is_on(self):
        return bool(self.coordinator.data.get(self._room_id, {}).get("open_window"))
    @property
    def device_info(self):
        return self._dev

async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    home_id = data["home_id"]
    entities = []
    for rid, name in data["rooms"].items():
        entities.append(IntuisPresenceSensor(coordinator, home_id, rid, name))
        entities.append(IntuisWindowSensor(coordinator, home_id, rid, name))
    async_add_entities(entities)
