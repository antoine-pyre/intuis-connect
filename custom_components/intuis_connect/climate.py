"""Climate platform for Intuis Connect."""
from homeassistant.components.climate import ClimateEntity, HVACMode, HVACAction, ClimateEntityFeature
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN

SUPPORTED_FEATURES = ClimateEntityFeature.TARGET_TEMPERATURE

class IntuisClimate(CoordinatorEntity, ClimateEntity):
    def __init__(self, coordinator, api, home_id, room_id, name):
        super().__init__(coordinator)
        self._api = api
        self._home_id = home_id
        self._room_id = room_id
        self._attr_name = name
        self._attr_unique_id = f"{room_id}_climate"
        self._attr_hvac_modes = [HVACMode.AUTO, HVACMode.HEAT, HVACMode.OFF]
        self._attr_supported_features = SUPPORTED_FEATURES
        self._attr_temperature_unit = self.hass.config.units.temperature_unit
        self._attr_min_temp = 7
        self._attr_max_temp = 30
        self._attr_target_temperature_step = 0.5

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
        if mode in ("home", "program", "schedule"):
            return HVACMode.AUTO
        return HVACMode.HEAT

    @property
    def hvac_action(self):
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        return HVACAction.HEATING if self.coordinator.data.get(self._room_id, {}).get("heating") else HVACAction.IDLE

    async def async_set_temperature(self, **kwargs):
        temp = kwargs.get("temperature")
        await self._api.async_set_room_state(self._room_id, "manual", float(temp))
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode):
        if hvac_mode == HVACMode.OFF:
            await self._api.async_set_room_state(self._room_id, "off")
        elif hvac_mode == HVACMode.AUTO:
            await self._api.async_set_room_state(self._room_id, "home")
        else:
            await self._api.async_set_room_state(self._room_id, "manual", self.target_temperature or 20)
        await self.coordinator.async_request_refresh()

async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    api = data["api"]
    home_id = data["home_id"]
    entities = [IntuisClimate(coordinator, api, home_id, rid, name) for rid, name in data["rooms"].items()]
    async_add_entities(entities)
