
"""Binary sensors (presence, window, anticipation)."""
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .device import build_device_info
from .const import DOMAIN

class _Base(CoordinatorEntity, BinarySensorEntity):
    def __init__(self, coordinator, home_id, room_id, room_name, name, uid, device_class):
        super().__init__(coordinator)
        self._room_id = room_id
        self._attr_name = name
        self._attr_unique_id = uid
        self._attr_device_class = device_class
        self._dev = build_device_info(home_id, room_id, room_name)
    @property
    def device_info(self):
        return self._dev

class PresenceSensor(_Base):
    def __init__(self, coordinator, h, r, n):
        super().__init__(coordinator, h, r, n, f"{n} Presence", f"{r}_presence", BinarySensorDeviceClass.MOTION)
    @property
    def is_on(self):
        return self.coordinator.data["rooms"][self._room_id]["presence"]

class WindowSensor(_Base):
    def __init__(self, coordinator, h, r, n):
        super().__init__(coordinator, h, r, n, f"{n} Open Window", f"{r}_window", BinarySensorDeviceClass.WINDOW)
    @property
    def is_on(self):
        return self.coordinator.data["rooms"][self._room_id]["open_window"]

class AnticipationSensor(_Base):
    def __init__(self, coordinator, h, r, n):
        super().__init__(coordinator, h, r, n, f"{n} Anticipation", f"{r}_anticipation", BinarySensorDeviceClass.HEAT)
    @property
    def is_on(self):
        return self.coordinator.data["rooms"][self._room_id]["anticipation"]

async def async_setup_entry(hass, entry, async_add_entities):
    d = hass.data[DOMAIN][entry.entry_id]
    ent=[]
    for rid, name in d["rooms"].items():
        ent.extend([
            # PresenceSensor(d["coordinator"], d["home_id"], rid, name),
            # WindowSensor(d["coordinator"], d["home_id"], rid, name),
            AnticipationSensor(d["coordinator"], d["home_id"], rid, name),
        ])
    async_add_entities(ent)
