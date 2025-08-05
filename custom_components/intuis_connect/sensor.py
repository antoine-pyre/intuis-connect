"""Sensor platform for Intuis Connect."""
from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import UnitOfTemperature, UnitOfEnergy
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .entity.intuis_entity import IntuisEntity
from .helper import get_basic_utils
from .intuis_data import IntuisRoom

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Intuis Connect sensors from a config entry."""
    coordinator, home_id, rooms, api = get_basic_utils(hass, entry)

    entities: list[IntuisSensor] = []
    for room_id in rooms:
        entities.append(IntuisTemperatureSensor(coordinator, home_id, rooms.get(room_id)))
        entities.append(IntuisTargetTemperatureSensor(coordinator, home_id, rooms.get(room_id)))
        entities.append(IntuisMullerTypeSensor(coordinator, home_id, rooms.get(room_id)))
        # entities.append(IntuisEnergySensor(coordinator, home_id, rooms.get(room_id)))
        entities.append(IntuisMinutesSensor(coordinator, home_id, rooms.get(room_id)))
    async_add_entities(entities, update_before_add=True)


class IntuisSensor(CoordinatorEntity, SensorEntity, IntuisEntity):
    """Generic sensor for an Intuis Connect room metric."""

    def __init__(
            self,
            coordinator,
            home_id: str,
            room: IntuisRoom,
            metric: str,
            label: str,
            unit: str | None,
            device_class: str | None,
    ) -> None:
        """Initialize the sensor."""
        CoordinatorEntity.__init__(self, coordinator)
        SensorEntity.__init__(self)
        IntuisEntity.__init__(self, coordinator, room, home_id, f"{room.name} {label}", metric)

        self._metric = metric
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class

    @property
    def native_value(self) -> float | int | None:
        """Return the current value of this sensor."""
        raise NotImplementedError(
            f"Subclasses of IntuisSensor must implement native_value for {self._metric}"
        )


class IntuisMullerTypeSensor(IntuisSensor):
    """Specialized sensor for device type."""

    def __init__(self, coordinator, home_id: str, room: IntuisRoom) -> None:
        """Initialize the muller type sensor."""
        super().__init__(
            coordinator,
            home_id,
            room,
            "muller_type",
            "Device Type",
            unit=None,
            device_class=None,
        )
        self._attr_icon = "mdi:device-hub"
        self._attr_available = False

    @property
    def native_value(self) -> str:
        """Return the current device type."""
        # Ensure we handle None values gracefully
        muller_type = self._room.muller_type
        if muller_type is None:
            return ""
        return muller_type


class IntuisTargetTemperatureSensor(IntuisSensor):
    """Specialized sensor for target temperature."""

    def __init__(self, coordinator, home_id: str, room: IntuisRoom) -> None:
        """Initialize the target temperature sensor."""
        super().__init__(
            coordinator,
            home_id,
            room,
            "target_temperature",
            "Setpoint",
            UnitOfTemperature.CELSIUS,
            None,
        )
        self._attr_icon = "mdi:thermometer"

    @property
    def native_value(self) -> float:
        """Return the current target temperature."""
        # Ensure we handle None values gracefully
        target_temp = self._room.target_temperature
        if target_temp is None:
            return 0.0
        return target_temp


class IntuisTemperatureSensor(IntuisSensor):
    """Specialized sensor for temperature data."""

    def __init__(self, coordinator, home_id: str, room: IntuisRoom) -> None:
        """Initialize the temperature sensor."""
        super().__init__(
            coordinator,
            home_id,
            room,
            "temperature",
            "Temperature",
            UnitOfTemperature.CELSIUS,
            "temperature",
        )
        self._attr_icon = "mdi:thermometer"

    @property
    def native_value(self) -> float:
        """Return the current temperature value."""
        # Ensure we handle None values gracefully
        temperature = self._room.temperature
        if temperature is None:
            return 0.0
        return temperature


class IntuisMinutesSensor(IntuisSensor):
    """Specialized sensor for heating minutes."""

    def __init__(self, coordinator, home_id: str, room: IntuisRoom) -> None:
        """Initialize the minutes sensor."""
        super().__init__(
            coordinator,
            home_id,
            room,
            "minutes",
            "Heating Minutes",
            "min",
            None,
        )
        self._attr_icon = "mdi:timer"

    @property
    def native_value(self) -> int:
        """Return the current heating minutes value."""
        # Ensure we handle None values gracefully
        minutes = self._room.minutes
        if minutes is None:
            return 0
        return minutes


class IntuisEnergySensor(IntuisSensor):
    """Specialized sensor for energy data."""

    def __init__(self, coordinator, home_id: str, room: IntuisRoom) -> None:
        """Initialize the energy sensor."""
        super().__init__(
            coordinator,
            home_id,
            room,
            "energy",
            "Energy Today",
            UnitOfEnergy.KILO_WATT_HOUR,
            "energy",
        )
        self._attr_icon = "mdi:flash"

    @property
    def native_value(self) -> float:
        """Return the current energy value."""
        # Ensure we handle None values gracefully
        energy = self._room.energy
        if energy is None:
            return 0.0
        return energy
