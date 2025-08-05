"""Climate platform for Intuis Connect."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import IntuisAPI
from .const import PRESET_AWAY, PRESET_BOOST, PRESET_SCHEDULE, API_MODE_OFF, API_MODE_AUTO, API_MODE_MANUAL, \
    API_MODE_AWAY, API_MODE_BOOST, API_MODE_HOME, DEFAULT_AWAY_TEMP, DEFAULT_AWAY_DURATION, DEFAULT_BOOST_TEMP, \
    DEFAULT_BOOST_DURATION
from .entity.intuis_entity import IntuisEntity, IntuisDataUpdateCoordinator
from .helper import get_basic_utils
from .intuis_data import IntuisRoom

_LOGGER = logging.getLogger(__name__)


class IntuisConnectClimate(
    CoordinatorEntity[IntuisDataUpdateCoordinator], ClimateEntity, IntuisEntity
):
    """Climate entity for an Intuis Connect-compatible device."""

    _attr_hvac_modes = [HVACMode.AUTO, HVACMode.HEAT, HVACMode.OFF]
    _attr_preset_modes = [PRESET_AWAY, PRESET_BOOST, PRESET_SCHEDULE]
    _attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE
    )
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_has_entity_name = True

    def __init__(
            self,
            coordinator: IntuisDataUpdateCoordinator,
            home_id: str,
            room: IntuisRoom,
            api: IntuisAPI,
    ) -> None:
        """Initialize the climate entity."""
        CoordinatorEntity.__init__(self, coordinator)
        ClimateEntity.__init__(self)
        IntuisEntity.__init__(self, coordinator, room, home_id, f"{room.name} Climate", "climate")
        self._home_id = home_id
        self._api = api
        self._attr_assumed_state = True
        self._attr_hvac_mode: HVACMode | None = None
        self._attr_preset_mode: str | None = None
        self._attr_target_temperature: float | None = None

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return self._attr_device_info

    @property
    def current_temperature(self) -> StateType:
        """Return the current temperature."""
        return self._get_room().temperature

    @property
    def target_temperature(self) -> StateType:
        """Return the target temperature."""
        if self._attr_target_temperature is not None:
            return self._attr_target_temperature
        return self._get_room().target_temperature

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return hvac operation ie. heat, cool mode."""
        if self._attr_hvac_mode is not None:
            return self._attr_hvac_mode
        mode = self._get_room().mode
        if mode == API_MODE_OFF:
            return HVACMode.OFF
        if mode == API_MODE_AUTO:
            return HVACMode.AUTO
        if mode in (API_MODE_MANUAL, API_MODE_AWAY, API_MODE_BOOST):
            return HVACMode.HEAT
        _LOGGER.warning("Unhandled HVAC mode: %s", mode)
        return HVACMode.HEAT

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode."""
        if self._attr_preset_mode is not None:
            return self._attr_preset_mode
        mode = self._get_room().mode
        if mode == API_MODE_AWAY:
            return PRESET_AWAY
        if mode == API_MODE_BOOST:
            return PRESET_BOOST
        return PRESET_SCHEDULE if self.hvac_mode == HVACMode.AUTO else None

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return the current running hvac operation."""
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        return (
            HVACAction.HEATING
            if self._get_room().heating
            else HVACAction.IDLE
        )

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temp = kwargs.get("temperature")
        if temp is None:
            return
        await self._api.async_set_room_state(
            self._get_room().id, API_MODE_MANUAL, float(temp)
        )
        self._attr_target_temperature = temp
        self._attr_hvac_mode = HVACMode.HEAT
        self._attr_preset_mode = None
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new hvac mode."""
        if hvac_mode == HVACMode.OFF:
            await self._api.async_set_room_state(self._get_room().id, API_MODE_OFF)
        elif hvac_mode == HVACMode.AUTO:
            await self._api.async_set_room_state(self._get_room().id, API_MODE_HOME)
        elif hvac_mode == HVACMode.HEAT:
            await self._api.async_set_room_state(
                self._get_room().id, API_MODE_MANUAL, float(self.target_temperature or 20.0)
            )
        self._attr_hvac_mode = hvac_mode
        if hvac_mode == HVACMode.AUTO:
            self._attr_preset_mode = PRESET_SCHEDULE
        else:
            self._attr_preset_mode = None
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        if preset_mode == PRESET_SCHEDULE:
            await self._api.async_set_room_state(self._get_room().id, API_MODE_HOME)
            self._attr_hvac_mode = HVACMode.AUTO
        elif preset_mode == PRESET_AWAY:
            await self._api.async_set_room_state(
                self._get_room().id,
                API_MODE_AWAY,
                DEFAULT_AWAY_TEMP,
                DEFAULT_AWAY_DURATION,
            )
            self._attr_hvac_mode = HVACMode.HEAT
        elif preset_mode == PRESET_BOOST:
            await self._api.async_set_room_state(
                self._get_room().id,
                API_MODE_BOOST,
                DEFAULT_BOOST_TEMP,
                DEFAULT_BOOST_DURATION,
            )
            self._attr_hvac_mode = HVACMode.HEAT
        self._attr_preset_mode = preset_mode
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()


async def async_setup_entry(
        hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the climate entities."""
    coordinator, home_id, rooms, api = get_basic_utils(hass, entry)

    entities = []
    for room_id in rooms:
        entities.append(
            IntuisConnectClimate(coordinator, home_id, rooms.get(room_id), api)
        )
    async_add_entities(entities, update_before_add=True)
