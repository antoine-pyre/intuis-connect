
"""Climate platform for Intuis Connect."""
from homeassistant.components.climate import ClimateEntity, HVACAction, HVACMode, ClimateEntityFeature
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers.update_coordinator import CoordinatorEntity
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

    @property
    def device_info(self):
        return self._dev_info

    @property
    def current_temperature(self):
        return self.coordinator.data["rooms"][self._room_id]["temperature"]

    @property
    def target_temperature(self):
        return self.coordinator.data["rooms"][self._room_id]["target_temperature"]

    @property
    def hvac_mode(self):
        mode = self.coordinator.data["rooms"][self._room_id]["mode"]
        if mode in ("off", "hg"):
            return HVACMode.OFF
        if mode in ("home", "schedule", "program"):
            return HVACMode.AUTO
        return HVACMode.HEAT

    @property
    def preset_mode(self):
        mode = self.coordinator.data["rooms"][self._room_id]["mode"]
        if mode == "away":
            return PRESET_AWAY
        if mode == "boost":
            return PRESET_BOOST
        return PRESET_SCHEDULE if self.hvac_mode == HVACMode.AUTO else None

    @property
    def hvac_action(self):
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        return HVACAction.HEATING if self.coordinator.data["rooms"][self._room_id]["heating"] else HVACAction.IDLE

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
            await self._api.async_set_room_state(self._room_id, "manual", float(self.target_temperature or 20.0))
        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode: str):
        if preset_mode == PRESET_SCHEDULE:
            await self._api.async_set_room_state(self._room_id, "home")
        elif preset_mode == PRESET_AWAY:
            await self._api.async_set_room_state(self._room_id, "manual", 16.0, 1440)
        elif preset_mode == PRESET_BOOST:
            await self._api.async_set_room_state(self._room_id, "manual", 30.0, 30)
        await self.coordinator.async_request_refresh()

async def async_setup_entry(hass, entry, async_add_entities):
    d = hass.data[DOMAIN][entry.entry_id]
    entities = [IntuisClimate(d["coordinator"], d["api"], d["home_id"], rid, name) for rid, name in d["rooms"].items()]
    async_add_entities(entities)
