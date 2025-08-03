"""Sensor platform for Intuis Connect."""
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .device import build_device_info
from .const import DOMAIN

class IntuisTemperatureSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, home_id, room_id, room_name):
        super().__init__(coordinator)
        self._room_id = room_id
        self._device_info = build_device_info(home_id, room_id, room_name)
        self._attr_name = f"{room_name} Temperature"
        self._attr_unique_id = f"{room_id}_temp"
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_native_unit_of_measurement = "°C"
        self._attr_state_class = SensorStateClass.MEASUREMENT
    @property
    def native_value(self):
        return self.coordinator.data.get(self._room_id, {}).get("temperature")
    @property
    def device_info(self): return self._device_info

class IntuisSetpointSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, home_id, room_id, room_name):
        super().__init__(coordinator)
        self._room_id = room_id
        self._device_info = build_device_info(home_id, room_id, room_name)
        self._attr_name = f"{room_name} Setpoint"
        self._attr_unique_id = f"{room_id}_setpoint"
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_native_unit_of_measurement = "°C"
        self._attr_state_class = SensorStateClass.MEASUREMENT
    @property
    def native_value(self):
        return self.coordinator.data.get(self._room_id, {}).get("target_temperature")
    @property
    def device_info(self): return self._device_info

class IntuisPowerSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, home_id, room_id, room_name):
        super().__init__(coordinator)
        self._room_id = room_id
        self._device_info = build_device_info(home_id, room_id, room_name)
        self._attr_name = f"{room_name} Heating Power"
        self._attr_unique_id = f"{room_id}_power"
        self._attr_native_unit_of_measurement = "%"
        self._attr_state_class = SensorStateClass.MEASUREMENT
    @property
    def native_value(self):
        return self.coordinator.data.get(self._room_id, {}).get("power")
    @property
    def device_info(self): return self._device_info

async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    home_id = data["home_id"]
    entities = []
    for rid, name in data["rooms"].items():
        entities.append(IntuisTemperatureSensor(coordinator, home_id, rid, name))
        entities.append(IntuisSetpointSensor(coordinator, home_id, rid, name))
        entities.append(IntuisPowerSensor(coordinator, home_id, rid, name))
    async_add_entities(entities)
