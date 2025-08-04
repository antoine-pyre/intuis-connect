"""Climate platform for Intuis Connect."""
import logging

from homeassistant.components.climate import ClimateEntity, HVACAction, HVACMode, ClimateEntityFeature
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    PRESET_AWAY,
    PRESET_BOOST,
    PRESET_SCHEDULE,
    DEFAULT_AWAY_TEMP,
    DEFAULT_AWAY_DURATION,
    DEFAULT_BOOST_TEMP,
    DEFAULT_BOOST_DURATION,
    API_MODE_OFF,
    API_MODE_HOME,
    API_MODE_MANUAL,
    API_MODE_AWAY,
    API_MODE_BOOST,
)
from .device import build_device_info
from .helper import get_room_name, get_room

_LOGGER = logging.getLogger(__name__)

RETRY_DELAY = 1  # seconds


class IntuisConnectClimate(CoordinatorEntity, ClimateEntity):
    """Climate entity for an Intuis Connect-compatible device."""

    _attr_hvac_modes = [HVACMode.AUTO, HVACMode.HEAT, HVACMode.OFF]
    _attr_preset_modes = [PRESET_SCHEDULE, PRESET_AWAY, PRESET_BOOST]
    _attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE
    )
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_has_entity_name = True

    def __init__(self, coordinator, home_id, room_id, api):
        super().__init__(coordinator)
        self._attr_target_temperature = None
        self._attr_hvac_mode = None
        self._attr_preset_mode = None
        self._home_id = home_id
        self._room_id = room_id
        self._attr_name = get_room_name(coordinator, room_id)
        self._attr_unique_id = f"{self._home_id}_{self._room_id}"
        self._api = api
        self._attr_assumed_state = True

    @property
    def device_info(self):
        return build_device_info(self._home_id, self._room_id, self._attr_name)

    @property
    def current_temperature(self):
        return get_room(self.coordinator, self._room_id)["temperature"]

    @property
    def target_temperature(self):
        return get_room(self.coordinator, self._room_id)["target_temperature"]

    @property
    def hvac_mode(self):
        """Return hvac operation ie. heat, cool mode."""
        mode = get_room(self.coordinator, self._room_id)["mode"]
        if mode == API_MODE_OFF:
            return HVACMode.OFF
        if mode == API_MODE_HOME:
            return HVACMode.AUTO
        if mode in (API_MODE_MANUAL, API_MODE_AWAY, API_MODE_BOOST):
            return HVACMode.HEAT
        _LOGGER.warning("Unhandled HVAC mode: %s", mode)
        return HVACMode.HEAT

    @property
    def preset_mode(self):
        mode = get_room(self.coordinator, self._room_id)["mode"]
        if mode == API_MODE_AWAY:
            return PRESET_AWAY
        if mode == API_MODE_BOOST:
            return PRESET_BOOST
        return PRESET_SCHEDULE if self.hvac_mode == HVACMode.AUTO else None

    @property
    def hvac_action(self):
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        return (
            HVACAction.HEATING
            if get_room(self.coordinator, self._room_id)["heating"]
            else HVACAction.IDLE
        )

    async def async_set_temperature(self, **kwargs):
        temp = kwargs.get("temperature")
        if temp is None:
            return
        self._attr_target_temperature = temp
        self._attr_hvac_mode = HVACMode.HEAT
        self._attr_preset_mode = None
        self.async_write_ha_state()
        await self._api.async_set_room_state(
            self._room_id, API_MODE_MANUAL, float(temp)
        )
        await self._request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode):
        """Set the HVAC mode."""

        self._attr_hvac_mode = hvac_mode
        if hvac_mode == HVACMode.AUTO:
            self._attr_preset_mode = PRESET_SCHEDULE
        else:
            self._attr_preset_mode = None

        self.async_write_ha_state()

        async def _do_set_hvac_mode():
            # Determine API mode and target temperature based on HVAC mode
            api_mode = None
            target_temp = None  # Default to 20 if no target temp set
            if hvac_mode == HVACMode.OFF:
                api_mode = API_MODE_OFF
            elif hvac_mode == HVACMode.AUTO:
                api_mode = API_MODE_HOME
            elif hvac_mode == HVACMode.HEAT:
                api_mode = API_MODE_MANUAL
                target_temp = float(self.target_temperature or 20.0)
            try:
                await self._api.async_set_room_state(self._room_id, api_mode, target_temp)
            except Exception as e:
                _LOGGER.error("Failed to set HVAC mode %s for room %s: %s", hvac_mode, self._room_id, e)
            finally:
                await self._request_refresh()

        self.hass.async_create_task(_do_set_hvac_mode())

    async def async_set_preset_mode(self, preset_mode: str):
        self._attr_preset_mode = preset_mode
        self.async_write_ha_state()

        async def _do_set_preset_mode():
            api_mode = None
            temp = None
            duration = None

            if preset_mode == PRESET_SCHEDULE:
                api_mode = API_MODE_HOME
                temp = None  # No specific temperature for schedule mode
                duration = None
                self._attr_hvac_mode = HVACMode.AUTO
            elif preset_mode == PRESET_AWAY:
                api_mode = API_MODE_AWAY
                temp = DEFAULT_AWAY_TEMP
                duration = DEFAULT_AWAY_DURATION
                self._attr_hvac_mode = HVACMode.HEAT
            elif preset_mode == PRESET_BOOST:
                api_mode = API_MODE_BOOST
                temp = DEFAULT_BOOST_TEMP
                duration = DEFAULT_BOOST_DURATION
                self._attr_hvac_mode = HVACMode.HEAT
            try:
                await self._api.async_set_room_state(self._room_id, api_mode, temp, duration)
            except Exception as e:
                _LOGGER.error("Failed to set preset mode %s for room %s: %s", preset_mode, self._room_id, e)
            finally:
                await self._request_refresh()
        self.hass.async_create_task(_do_set_preset_mode())


    async def _request_refresh(self):
        """Request a refresh of the coordinator data."""
        _LOGGER.debug("Requesting refresh for room %s", self._room_id)
        await self.coordinator.async_request_refresh()


async def async_setup_entry(hass, entry, async_add_entities):
    d = hass.data[DOMAIN][entry.entry_id]
    api = d["api"]
    coordinator = d["coordinator"]
    home_id = coordinator.data["id"]
    entities = [
        IntuisConnectClimate(coordinator, home_id, room_id, api)
        for room_id in coordinator.data["rooms"]
    ]
    async_add_entities(entities)
