"""Climate platform for Intuis Connect."""
from homeassistant.components.climate import ClimateEntity, HVACMode, HVACAction, ClimateEntityFeature
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import UnitOfTemperature

from .const import DOMAIN, SUPPORTED_PRESETS, PRESET_SCHEDULE, PRESET_AWAY, PRESET_BOOST
from .device import build_device_info

SUPPORT_FLAGS = ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE

class IntuisClimate(CoordinatorEntity, ClimateEntity):
    _attr_supported_features = SUPPORT_FLAGS
    _attr_hvac_modes = [HVACMode.AUTO, HVACMode.HEAT, HVACMode.OFF]
    _attr_preset_modes = SUPPORTED_PRESETS
    _attr_min_temp = 7.0
    _attr_max_temp = 30.0
    _attr_target_temperature_step = 0.5
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    
    def __init__(self, coordinator, api, home_id, room_id, room_name):
        super().__init__(coordinator)
        self._api = api
        self._home_id = home_id
        self._room_id = room_id
        self._attr_name = room_name
        self._attr_unique_id = f"{room_id}_climate"
        self._dev_info = build_device_info(home_id, room_id, room_name)

    # device registry
    @property
    def device_info(self):
        return self._dev_info

    # state properties
    @property
    def current_temperature(self):
        return self.coordinator.data.get(self._room_id, {}).get("temperature")

    @property
    def target_temperature(self):
        return self.coordinator.data.get(self._room_id, {}).get("target_temperature")

    @property
    def hvac_mode(self):
        mode = self.coordinator.data.get(self._room_id, {}).get("mode")
        if mode in ("off", "hg"):
            return HVACMode.OFF
        if mode in ("home", "schedule", "program"):
            return HVACMode.AUTO
        return HVACMode.HEAT

    @property
    def preset_mode(self):
        mode = self.coordinator.data.get(self._room_id, {}).get("mode")
        if mode == "away":
            return PRESET_AWAY
        if mode == "boost":
            return PRESET_BOOST
        return PRESET_SCHEDULE if self.hvac_mode == HVACMode.AUTO else None

    @property
    def hvac_action(self):
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        if self.coordinator.data.get(self._room_id, {}).get("heating"):
            return HVACAction.HEATING
        return HVACAction.IDLE

    async def async_set_temperature(self, **kwargs):
        temp = kwargs.get("temperature")
        if temp is None:
            return
        await self._api.async_set_room_state(self._room_id, "manual", float(temp))
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode):
        if hvac_mode == HVACMode.OFF:
            await self._api.async_set_room_state(self._room_id, "off")
        elif hvac_mode == HVACMode.AUTO:
            await self._api.async_set_room_state(self._room_id, "home")
        elif hvac_mode == HVACMode.HEAT:
            await self._api.async_set_room_state(
                self._room_id, "manual", float(self.target_temperature or 20.0)
            )
        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode: str):
        if preset_mode == PRESET_SCHEDULE:
            await self._api.async_set_room_state(self._room_id, "home")
        elif preset_mode == PRESET_AWAY:
            dur = self.hass.config_entries.async_get_entry(self.coordinator.config_entry_id).options.get("away_duration", 1440)
            temp = self.hass.config_entries.async_get_entry(self.coordinator.config_entry_id).options.get("away_temp", 16.0)
            await self._api.async_set_room_state(self._room_id, "manual", temp, dur)
        elif preset_mode == PRESET_BOOST:
            dur = self.hass.config_entries.async_get_entry(self.coordinator.config_entry_id).options.get("boost_duration", 30)
            temp = self.hass.config_entries.async_get_entry(self.coordinator.config_entry_id).options.get("boost_temp", 30.0)
            await self._api.async_set_room_state(self._room_id, "manual", temp, dur)
        await self.coordinator.async_request_refresh()

async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    api = data["api"]
    home_id = data["home_id"]
    entities = [IntuisClimate(coordinator, api, home_id, rid, name) for rid, name in data["rooms"].items()]
    async_add_entities(entities)
