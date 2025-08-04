"""Sensor platform for Intuis Connect."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import UnitOfTemperature, UnitOfEnergy, UnitOfPower
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .device import build_device_info

_LOGGER = logging.getLogger(__name__)

# Define the metrics you want: key in data, human label, unit, device_class string
SENSOR_TYPES: dict[str, tuple[str, str, str]] = {
    "temperature": ("Temperature", UnitOfTemperature.CELSIUS, "temperature"),
    "target_temperature": ("Setpoint", UnitOfTemperature.CELSIUS, None),
    "power": ("Heating Power", UnitOfPower.WATT, "power"),
    "energy": ("Energy Today", UnitOfEnergy.KILO_WATT_HOUR, "energy"),
    "minutes": ("Heating Minutes", "min", None),
}

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Intuis Connect sensors from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    home_id = data["api"].home_id
    rooms = data["rooms"]

    entities: list[IntuisSensor] = []
    for room_id, room_name in rooms.items():
        for metric, (label, unit, device_class) in SENSOR_TYPES.items():
            entities.append(
                IntuisSensor(
                    coordinator,
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
    """Generic sensor for an Intuis Connect room metric."""

    def __init__(
            self,
            coordinator,
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
        self._home_id = home_id
        self._room_id = room_id
        self._metric = metric
        self._attr_name = f"{room_name} {label}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_unique_id = f"{home_id}_{room_id}_{metric}"
        # Point to the same device as the thermostat, etc.
        self._attr_device_info = build_device_info(home_id, room_id, room_name)

    @property
    def native_value(self) -> float | int | None:
        """Return the current value of this sensor."""
        rooms = self.coordinator.data.get("rooms", {})
        room = rooms.get(self._room_id)
        _LOGGER.debug("Fetching %s for room %s: %s", self._metric, self._room_id, room.get(self._metric))
        if room is None:
            return None
        return room.get(self._metric)

    @property
    def device_info(self):
        """Return device registry info."""
        return self._attr_device_info
