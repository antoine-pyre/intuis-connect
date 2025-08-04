"""Sensors for Intuis Connect (temperature, setpoint, power, energy, heating minutes)."""

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .device import build_device_info


class _Base(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, home_id, room_id, room_name):
        super().__init__(coordinator)
        self._room_id = room_id
        self._dev = build_device_info(home_id, room_id, room_name)

    @property
    def device_info(self):
        return self._dev


# ---------------------------------------------------------------------- live sensors
class TemperatureSensor(_Base):
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = "°C"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, home, room, name):
        super().__init__(coordinator, home, room, name)
        self._attr_name = f"{name} Temperature"
        self._attr_unique_id = f"{room}_temp"

    @property
    def native_value(self):
        return self.coordinator.data["rooms"][self._room_id]["temperature"]


class SetpointSensor(_Base):
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = "°C"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, home, room, name):
        super().__init__(coordinator, home, room, name)
        self._attr_name = f"{name} Setpoint"
        self._attr_unique_id = f"{room}_setpoint"

    @property
    def native_value(self):
        return self.coordinator.data["rooms"][self._room_id]["target_temperature"]


class PowerSensor(_Base):
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, home, room, name):
        super().__init__(coordinator, home, room, name)
        self._attr_name = f"{name} Heating Power"
        self._attr_unique_id = f"{room}_power"

    @property
    def native_value(self):
        return self.coordinator.data["rooms"][self._room_id]["power"]


# ---------------------------------------------------------------------- calculated sensors
class EnergySensor(_Base):
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = "kWh"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, coordinator, home, room, name):
        super().__init__(coordinator, home, room, name)
        self._attr_name = f"{name} Energy"
        self._attr_unique_id = f"{room}_energy"

    @property
    def native_value(self):
        return self.coordinator.data["rooms"][self._room_id]["energy"]


class HeatingMinutesSensor(_Base):
    _attr_native_unit_of_measurement = "min"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, coordinator, home, room, name):
        super().__init__(coordinator, home, room, name)
        self._attr_name = f"{name} Heating Minutes"
        self._attr_unique_id = f"{room}_heat_minutes"

    @property
    def native_value(self):
        return self.coordinator.data["rooms"][self._room_id]["minutes"]


async def async_setup_entry(hass, entry, async_add_entities):
    d = hass.data[DOMAIN][entry.entry_id]
    coordinator = d["coordinator"]
    home_id = coordinator.data["id"]

    ents = []
    for room_id, room_data in coordinator.data["rooms"].items():
        room_name = room_data["name"]
        ents.extend(
            [
                TemperatureSensor(coordinator, home_id, room_id, room_name),
                SetpointSensor(coordinator, home_id, room_id, room_name),
                PowerSensor(coordinator, home_id, room_id, room_name),
                EnergySensor(coordinator, home_id, room_id, room_name),
                HeatingMinutesSensor(coordinator, home_id, room_id, room_name),
            ]
        )
    async_add_entities(ents)
