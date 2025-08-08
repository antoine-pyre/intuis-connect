"""Home-level device and entities for Intuis Connect."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .intuis_home import IntuisHome
from ..entity.intuis_entity import IntuisDataUpdateCoordinator
from ..utils.const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class IntuisHomeEntity(CoordinatorEntity[IntuisDataUpdateCoordinator], SensorEntity):
    """Base class for Intuis home-level entities."""

    def __init__(
            self,
            coordinator: IntuisDataUpdateCoordinator,
            home_id: str,
            entity_type: str,
            home_property: str,
            icon: str,
            available: bool = False,
            measurement: bool = False,
    ) -> None:
        """Initialize the home entity."""
        super().__init__(coordinator)
        self._home_id = home_id
        self._attr_name = f"Intuis Home {home_property}"
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
        self._attr_available = available
        self._attr_entity_registry_enabled_default = False
        if measurement:
            self._attr_state_class = SensorStateClass.MEASUREMENT

    def _get_home(self) -> IntuisHome:
        """Get the home data from coordinator."""
        return self.coordinator.data.get("intuis_home")

    @property
    def native_value(self) -> Any:
        """Return the value of the home property."""
        home_data = self._get_home()
        if not home_data:
            _LOGGER.warning("Home data not available for home ID %s", self._home_id)
            return None

        try:
            # Use operator.attrgetter for potentially nested attributes
            from operator import attrgetter
            getter = attrgetter(self._property)
            return getter(home_data)
        except AttributeError as e:
            _LOGGER.error(
                "Failed to get property '%s' from home_data: %s",
                self._property,
                str(e)
            )
            return None

class IntuisHomeConfigEntity(IntuisHomeEntity):
    """Base class for Intuis home-level configuration entities."""

    def __init__(
            self,
            coordinator: IntuisDataUpdateCoordinator,
            home_id: str,
            entity_type: str,
            home_property: str,
            icon: str,
            available: bool = False,
            measurement: bool = False,
    ) -> None:
        """Initialize the home configuration entity."""
        super().__init__(coordinator, home_id, entity_type, home_property, icon, measurement, available)

    def _get_home(self) -> IntuisHome:
        """Get the home data from coordinator."""
        return self.coordinator.data.get("home_config")


class IntuisHomeSensorDefinition:
    """Definition of a sensor entity for Intuis home-level data."""

    def __init__(self, entity_type: str, home_property: str, icon: str, measurement: bool = False, available: bool = False) -> None:
        """Initialize the sensor definition."""
        self.entity_type = entity_type
        self.home_property = home_property
        self.icon = icon
        self.measurement = measurement
        self.available = available


intuis_home_entities: list[IntuisHomeSensorDefinition] = [
    IntuisHomeSensorDefinition("Name", "name", "mdi:home", True),
    IntuisHomeSensorDefinition("Country", "country", "mdi:flag"),
    IntuisHomeSensorDefinition("Timezone", "timezone", "mdi:map-clock"),
    IntuisHomeSensorDefinition("Altitude", "altitude", "mdi:elevation-rise", False, True),
    IntuisHomeSensorDefinition("City", "city", "mdi:city"),
    IntuisHomeSensorDefinition("Currency Code", "currency_code", "mdi:currency-usd"),
    IntuisHomeSensorDefinition("Number of Users", "nb_users", "mdi:account-multiple"),
    IntuisHomeSensorDefinition("Temperature Control Mode", "temperature_control_mode", "mdi:thermometer",  True),
    IntuisHomeSensorDefinition("Thermostat Mode", "therm_mode", "mdi:thermostat", True),
    IntuisHomeSensorDefinition("Thermostat Setpoint Default Duration",
                               "therm_setpoint_default_duration", "mdi:timer-sand",  True),
    IntuisHomeSensorDefinition("Thermostat Heating Priority",
                               "therm_heating_priority", "mdi:priority-high",  True),
    IntuisHomeSensorDefinition("Contract Power Unit", "contract_power_unit", "mdi:flash", True),
]

intuis_home_config_entities: list[IntuisHomeSensorDefinition] = [
    IntuisHomeSensorDefinition("Absence Detection", "absence_detection", "mdi:account-off",  True),
    IntuisHomeSensorDefinition("Anticipation", "anticipation", "mdi:clock-fast",  True),
    IntuisHomeSensorDefinition("Balancing", "balancing", "mdi:balance-scale",  True),
    IntuisHomeSensorDefinition("Debug Enabled", "debug_enabled", "mdi:bug-check",  True),
    IntuisHomeSensorDefinition("Offload", "offload", "mdi:power-plug-off", True),
    IntuisHomeSensorDefinition("Open Window Detection", "open_window", "mdi:window-open-variant", True),
    IntuisHomeSensorDefinition("Presence Threshold", "presence_threshold", "mdi:eye-check-outline"),
    IntuisHomeSensorDefinition("Schedule Optimization", "schedule_optimization", "mdi:calendar-check-outline"),
    IntuisHomeSensorDefinition("Temperature Lowering Mode",
                               "temp_lowering_mode", "mdi:temperature-celsius"),
    IntuisHomeSensorDefinition("Thermostat Setpoint Day Color Red EJP Offset",
                               "therm_setpoint_day_color_red_ejp_offset", "mdi:thermometer-alert"),
    IntuisHomeSensorDefinition("Thermostat Setpoint Day Color Red EJP Type",
                               "therm_setpoint_day_color_red_ejp_type", "mdi:thermometer-alert"),
    IntuisHomeSensorDefinition("Thermostat Setpoint Day Color White Offset",
                               "therm_setpoint_day_color_white_offset", "mdi:thermometer-alert"),
    IntuisHomeSensorDefinition("Thermostat Setpoint Day Color White Type",
                               "therm_setpoint_day_color_white_type", "mdi:thermometer-alert"),
]

def provide_home_sensors(
        coordinator: IntuisDataUpdateCoordinator,
        home_id: str,
) -> list[SensorEntity]:
    """Set up home-level sensor entities."""

    result: list[SensorEntity] = []
    for entity_def in intuis_home_entities:
        result.append(
            IntuisHomeEntity(
                coordinator,
                home_id,
                entity_def.entity_type,
                entity_def.home_property,
                entity_def.icon,
                entity_def.measurement,
                entity_def.available
            )
        )
    for entity_def in intuis_home_config_entities:
        result.append(
            IntuisHomeConfigEntity(
                coordinator,
                home_id,
                entity_def.entity_type,
                entity_def.home_property,
                entity_def.icon,
                entity_def.measurement,
                entity_def.available
            )
        )
    return result
