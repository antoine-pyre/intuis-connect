"""Climate platform for Intuis Connect."""
import logging
import asyncio

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import HVAC_MODE_HEAT, PRESET_NONE
from homeassistant.const import ATTR_TEMPERATURE, PRECISION_WHOLE, TEMP_CELSIUS
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .device import build_device_info
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# How many times we'll retry the cloud call before giving up
MAX_ACTION_RETRIES = 3
# Delay between retries (and an extra delay after the first refresh)
RETRY_DELAY = 1  # seconds


class IntuisClimate(CoordinatorEntity, ClimateEntity):
    """Climate entity representing an Intuis Connect radiator."""

    _attr_temperature_unit = TEMP_CELSIUS
    _attr_precision = PRECISION_WHOLE

    def __init__(self, coordinator, api, home_id, room_id, room_name):
        super().__init__(coordinator)
        self._api = api
        self._home_id = home_id
        self._room_id = room_id
        self._attr_name = room_name
        self._attr_unique_id = f"{room_id}_climate"
        self._attr_device_info = build_device_info(
            home_id, room_id, room_name
        )

    @property
    def device_info(self):
        return self._attr_device_info

    @property
    def current_temperature(self):
        return self.coordinator.data["rooms"][self._room_id]["temperature"]

    @property
    def target_temperature(self):
        return self.coordinator.data["rooms"][self._room_id]["target_temperature"]

    @property
    def hvac_mode(self):
        return self.coordinator.data["rooms"][self._room_id]["mode"]

    @property
    def hvac_action(self):
        return HVAC_MODE_HEAT if self.coordinator.data["rooms"][self._room_id]["heating"] else None

    @property
    def preset_mode(self):
        return PRESET_NONE

    @staticmethod
    async def _execute_with_retry(func, *args, **kwargs):
        """Helper to retry an API call multiple times."""
        for attempt in range(1, MAX_ACTION_RETRIES + 1):
            try:
                return await func(*args, **kwargs)
            except Exception as err:
                _LOGGER.warning(
                    "Attempt %d/%d to call %s failed: %s",
                    attempt,
                    MAX_ACTION_RETRIES,
                    func.__name__,
                    err,
                )
                if attempt < MAX_ACTION_RETRIES:
                    await asyncio.sleep(RETRY_DELAY)
                else:
                    raise
        return None

    async def _refresh_twice(self):
        """Force two consecutive refreshes to ensure state consistency."""
        await self.coordinator.async_request_refresh()
        await asyncio.sleep(RETRY_DELAY)
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode):
        """Set HVAC mode with retry and then refresh twice."""
        # Map HA mode to your API parameters:
        if hvac_mode == HVAC_MODE_HEAT:
            api_mode = "manual"
            temp = self.target_temperature or 20.0
            # Some APIs need duration param too; adjust if needed
            await self._execute_with_retry(self._api.async_set_room_state, self._room_id, api_mode, float(temp))
        else:
            # For OFF or AUTO (home/schedule):
            mode_map = {"off": "off", "auto": "home"}
            api_mode = mode_map.get(hvac_mode, "home")
            await self._execute_with_retry(self._api.async_set_room_state, self._room_id, api_mode)

        await self._refresh_twice()

    async def async_set_temperature(self, **kwargs):
        """Set temperature with retry and then refresh twice."""
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        await self._execute_with_retry(self._api.async_set_room_state, self._room_id, "manual", float(temp))
        await self._refresh_twice()

async def async_setup_entry(hass, entry, async_add_entities):
    d = hass.data[DOMAIN][entry.entry_id]
    entities = [IntuisClimate(d["coordinator"], d["api"], d["home_id"], rid, name) for rid, name in d["rooms"].items()]
    async_add_entities(entities)
