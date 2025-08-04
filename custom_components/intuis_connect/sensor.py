"""Sensor platform for Intuis Connect."""
from __future__ import annotations
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import (
    TEMP_CELSIUS,
    ENERGY_KILO_WATT_HOUR,
    POWER_WATT,
    DEVICE_CLASS_TEMPERATURE,
    DEVICE_CLASS_ENERGY,
    DEVICE_CLASS_POWER,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .device import build_device_info

# List of metrics we expose, with (key, name, unit, device_class)
SENSOR_TYPES: dict[str, tuple[str, str, str]] = {
    "temperature": ("Temperature", TEMP_CELSIUS, DEVICE_CLASS_TEMPERATURE),
    "target_temperature": ("Setpoint", TEMP_CELSIUS, None),
    "heating_power_request": ("Heating Power", "W", DEVICE_CLASS_POWER),
    "energy": ("Energy Today", ENERGY_KILO_WATT_HOUR, DEVICE_CLASS_ENERGY),
    "minutes": ("Heating Minutes", "min", None),
}

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the Intuis Connect sensors from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    home_id = data["home_id"]
    rooms = data["rooms"]

    entities: list[IntuisSensor] = []
    for room_id, room_name in rooms.items():
        for metric, (label, unit, device_class) in SENSOR_TYPES.items():
            entities.append(
                IntuisSensor(
                    coordinator,
                    data["api"],
                    home_id,
                    room_id,
                    room_name,
                    metric,
                    label,
                    unit,
                    device_class,
                )
            )
    async_add_entities(entities)


class IntuisSensor(CoordinatorEntity, SensorEntity):
    """Generic Intuis Connect room sensor."""

    def __init__(
            self,
            coordinator,
            api: Any,
            home_id: str,
            room_id: str,
            room_name: str,
            metric: str,
            label: str,
            unit: str,
            device_class: str | None,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._api = api
        self._home_id = home_id
        self._room_id = room_id
        self._metric = metric
        self._attr_name = f"{room_name} {label}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_unique_id = f"{home_id}_{room_id}_{metric}"
        # Tie back to the same device as the climate entity
        self._attr_device_info = build_device_info(home_id, room_id, room_name)

    @property
    def native_value(self) -> float | int | None:
        """Return the current value of this sensor."""
        rooms = self.coordinator.data.get("rooms", {})
        room = rooms.get(self._room_id)
        if room is None:
            return None
        # Some metrics might be missing; default to None
        return room.get(self._metric)

    @property
    def device_info(self):
        """Return device registry information."""
        return self._attr_device_info
