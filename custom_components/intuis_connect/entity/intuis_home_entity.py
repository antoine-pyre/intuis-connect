"""Home-level device and entities for Intuis Connect."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .intuis_home import IntuisHome
from ..entity.intuis_entity import IntuisDataUpdateCoordinator
from ..utils.const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class IntuisHomeEntity(CoordinatorEntity[IntuisDataUpdateCoordinator], Entity):
    """Base class for Intuis home-level entities."""

    def __init__(
            self,
            coordinator: IntuisDataUpdateCoordinator,
            home_id: str,
            entity_type: str,
            name: str,
            home_property: str,
            icon: str,
            measurement: bool = False
    ) -> None:
        """Initialize the home entity."""
        super().__init__(coordinator)
        self._home_id = home_id
        self._attr_name = f"Intuis Home {name}"
        self._attr_unique_id = f"intuis_{home_id}_home_{entity_type}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{home_id}_home")},
            name="Intuis Home",
            manufacturer="Muller Intuitiv (Netatmo)",
            model="Home Controller",
            suggested_area="Home",
        )
        self._attr_icon = icon
        self._property = home_property
        if measurement:
            self._attr_state_class = SensorStateClass.MEASUREMENT

    def _get_home_data(self) -> IntuisHome:
        """Get the home data from coordinator."""
        return self.coordinator.data.get("home")

    @property
    def native_value(self) -> Any:
        """Return the value of the home property."""
        home_data = self._get_home_data()
        if home_data:
            return getattr(home_data, self._property, None)
        return None


class IntuisHomeCoordinatesSensor(IntuisHomeEntity, SensorEntity):
    """Sensor for home coordinates."""

    def __init__(
            self,
            coordinator: IntuisDataUpdateCoordinator,
            home_id: str,
            coordinate: str,  # "latitude" or "longitude"
    ) -> None:
        """Initialize the coordinates sensor."""
        SensorEntity.__init__(coordinator)
        IntuisHomeEntity.__init__(
            self, coordinator, home_id, coordinate, coordinate.capitalize(),
            coordinate, "mdi:crosshairs-gps", True
        )
        self._coordinate = coordinate

    @property
    def native_value(self) -> float | None:
        """Return the coordinate value."""
        coordinates = self._get_home_data().coordinates
        if coordinates and isinstance(coordinates, list) and len(coordinates) >= 2:
            return coordinates[0] if self._coordinate == "latitude" else coordinates[1]
        return None


class IntuisHomeFeatureSensor(IntuisHomeEntity, SensorEntity):
    """Generic sensor for boolean home features."""

    def __init__(
            self,
            coordinator: IntuisDataUpdateCoordinator,
            home_id: str,
            feature_key: str,
            feature_name: str,
            icon: str,
    ) -> None:
        """Initialize the feature sensor."""
        super().__init__(coordinator, home_id, feature_key, feature_name)
        self._feature_key = feature_key
        self._attr_icon = icon

    @property
    def native_value(self) -> str | None:
        """Return the feature status."""
        home_data = self._get_home_data()
        if home_data:
            value = getattr(home_data, self._property, None)
            return "Enabled" if value else "Disabled"
        else:
            _LOGGER.warning("Home data not available for feature %s", self._feature_key)
            return None


def provide_home_sensors(
        coordinator: IntuisDataUpdateCoordinator,
        home_id: str,
) -> list[SensorEntity]:
    """Set up home-level sensor entities."""
    return [
        IntuisHomeEntity(coordinator, home_id, "timezone", "Timezone", "timezone", "mdi:map-clock"),
        IntuisHomeEntity(coordinator, home_id, "country", "Country", "country", "mdi:flag"),
        IntuisHomeEntity(coordinator, home_id, "name", "Name", "name", "mdi:home"),
        IntuisHomeCoordinatesSensor(coordinator, home_id, "latitude"),
        IntuisHomeCoordinatesSensor(coordinator, home_id, "longitude"),
        IntuisHomeEntity(coordinator, home_id, "altitude", "Altitude", "altitude", "mdi:elevation-rise", True),
        IntuisHomeEntity(coordinator, home_id, "therm_mode", "Thermostat Mode", "therm_mode", "mdi:thermostat"),

        # Feature sensors
        IntuisHomeFeatureSensor(coordinator, home_id, "presence_settings_experiment", "Presence Experiment",
                                "mdi:motion-sensor"),
        IntuisHomeFeatureSensor(coordinator, home_id, "smart_room_enabled", "Smart Room", "mdi:brain"),
        IntuisHomeFeatureSensor(coordinator, home_id, "safety", "Safety Mode", "mdi:shield-check"),
        IntuisHomeFeatureSensor(coordinator, home_id, "frost_protection_enabled", "Frost Protection",
                                "mdi:snowflake-alert"),
    ]
