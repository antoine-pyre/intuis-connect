"""Climate platform for Intuis Connect."""
from __future__ import annotations

import logging
import time
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
from homeassistant.helpers.event import async_call_later

from .intuis_api.api import IntuisAPI
from .entity.intuis_room import IntuisRoom
from .utils.const import (
    PRESET_AWAY, PRESET_BOOST, PRESET_SCHEDULE, PRESET_FROST_PROTECT, API_MODE_OFF, API_MODE_AUTO, API_MODE_MANUAL,
    API_MODE_AWAY, API_MODE_BOOST, API_MODE_HG, API_MODE_HOME, DEFAULT_AWAY_TEMP, DEFAULT_AWAY_DURATION, DEFAULT_BOOST_TEMP,
    DEFAULT_BOOST_DURATION, DEFAULT_FROST_PROTECT_TEMP, DEFAULT_FROST_PROTECT_DURATION, DEFAULT_MANUAL_DURATION, DOMAIN,
    CONF_MANUAL_DURATION, CONF_AWAY_DURATION, CONF_BOOST_DURATION, CONF_FROST_PROTECT_DURATION,
    CONF_AWAY_TEMP, CONF_BOOST_TEMP, CONF_FROST_PROTECT_TEMP,
)
from .entity.intuis_entity import IntuisEntity, IntuisDataUpdateCoordinator
from .utils.helper import get_basic_utils

_LOGGER = logging.getLogger(__name__)


class IntuisConnectClimate(
    CoordinatorEntity[IntuisDataUpdateCoordinator], ClimateEntity, IntuisEntity
):
    """Climate entity for an Intuis Connect-compatible device."""

    _attr_hvac_modes = [HVACMode.AUTO, HVACMode.HEAT, HVACMode.OFF]
    _attr_preset_modes = [PRESET_AWAY, PRESET_BOOST, PRESET_SCHEDULE, PRESET_FROST_PROTECT]
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
            entry_id: str,
    ) -> None:
        """Initialize the climate entity."""
        CoordinatorEntity.__init__(self, coordinator)
        ClimateEntity.__init__(self)
        IntuisEntity.__init__(self, coordinator, room, home_id, f"{room.name} Climate", "climate")
        self._home_id = home_id
        self._api = api
        self._entry_id = entry_id
        # We have real state from the coordinator, not assumed state
        self._attr_assumed_state = False
        self._attr_hvac_mode: HVACMode | None = None
        self._attr_preset_mode: str | None = None
        self._attr_target_temperature: float | None = None

    def _get_overrides(self) -> dict[str, dict]:
        data = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {})
        return data.get("overrides", {})
    
    def _get_intuis_home(self):
        """Get the IntuisHome object from coordinator data."""
        return self.coordinator.data.get("intuis_home")

    def _get_save_overrides(self):
        """Get the save_overrides callback."""
        data = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {})
        return data.get("save_overrides")

    def _get_option(self, key: str, default: Any) -> Any:
        """Get an option value from the config entry."""
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        if entry:
            return entry.options.get(key, default)
        return default

    def _schedule_end_refresh(self, end_ts: int) -> None:
        # Schedule a refresh slightly after end time
        delay = max(0, end_ts - int(time.time()) + 1)
        def _cb(_now):
            self.hass.async_create_task(self.coordinator.async_request_refresh())
        async_call_later(self.hass, delay, _cb)

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
        return self._get_room().target_temperature

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return hvac operation ie. heat, cool mode."""
        if self._attr_hvac_mode is not None:
            return self._attr_hvac_mode
        mode = self._get_room().mode
        if mode == API_MODE_OFF:
            return HVACMode.OFF
        if mode in (API_MODE_AUTO, API_MODE_AWAY, API_MODE_HOME, API_MODE_HG):
            return HVACMode.AUTO
        if mode in (API_MODE_MANUAL, API_MODE_BOOST):
            return HVACMode.HEAT
        _LOGGER.warning("Unhandled HVAC mode: %s", mode)
        return HVACMode.HEAT

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode."""
        if self._attr_preset_mode is not None:
            return self._attr_preset_mode
        
        room = self._get_room()
        if not room:
            return None
        
        room_id = room.id
        
        # First, check overrides to see if away/boost mode is active
        # This is more reliable than therm_setpoint_mode which only returns "auto" or "manual"
        # Overrides are set when we programmatically set away/boost modes
        overrides = self._get_overrides()
        override = overrides.get(room_id)
        
        if override:
            override_mode = override.get("mode")
            if override_mode == API_MODE_AWAY:
                return PRESET_AWAY
            if override_mode == API_MODE_BOOST:
                return PRESET_BOOST
            if override_mode == API_MODE_HG:
                return PRESET_FROST_PROTECT
            # If override is manual, it's not a preset (user-set temperature)
            if override_mode == API_MODE_MANUAL:
                return None
        
        # Check room's boost_status (from API homestatus)
        # boost_status indicates "in_progress" when boost is active, "disabled" otherwise
        # This is the primary method to detect boost mode
        if room.boost_status == "in_progress":
            return PRESET_BOOST
        
        # Check home-level away mode indicators (from API homedata)
        # therm_absense_autoway indicates if auto-away is enabled
        # therm_absence_location might indicate if away mode is active
        intuis_home = self._get_intuis_home()
        if intuis_home:
            # If auto-away is enabled and we're in auto mode, could be away
            # But this is less reliable, so we prioritize overrides and room-level data
            pass  # Could add logic here if needed
        
        # Fallback: check therm_setpoint_mode (though it may not have away/boost)
        # This often only returns "auto" or "manual", not "away" or "boost"
        # But it can also return "hg" for Hors-Gel (Frost Protection) mode
        # Note: Some installations may return "boost" in therm_setpoint_mode for compatibility
        mode = room.mode
        if mode == API_MODE_AWAY:
            return PRESET_AWAY
        if mode == API_MODE_BOOST:
            # Fallback for installations that return boost in therm_setpoint_mode
            return PRESET_BOOST
        if mode == API_MODE_HG:
            return PRESET_FROST_PROTECT
        
        # If in AUTO mode, return schedule preset
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
        room_id = self._get_room().id
        manual_duration = self._get_option(CONF_MANUAL_DURATION, DEFAULT_MANUAL_DURATION)
        await self._api.async_set_room_state(
            room_id, API_MODE_MANUAL, float(temp), manual_duration
        )
        now_ts = int(time.time())
        end_ts = now_ts + manual_duration * 60
        overrides = self._get_overrides()
        overrides[room_id] = {
            "mode": API_MODE_MANUAL,
            "temp": float(temp),
            "end": end_ts,
            "sticky": True,
            "last_reapply": now_ts,
        }
        # Persist overrides to storage
        save_overrides = self._get_save_overrides()
        if save_overrides:
            await save_overrides()
        self._schedule_end_refresh(end_ts)
        self._attr_target_temperature = temp
        self._attr_hvac_mode = HVACMode.HEAT
        self._attr_preset_mode = None
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new hvac mode."""
        room_id = self._get_room().id
        overrides = self._get_overrides()
        overrides_changed = False

        if hvac_mode == HVACMode.OFF:
            await self._api.async_set_room_state(room_id, API_MODE_OFF)
            if room_id in overrides:
                overrides.pop(room_id, None)
                overrides_changed = True
            self._attr_hvac_mode = HVACMode.OFF
            self._attr_preset_mode = None
        elif hvac_mode == HVACMode.AUTO:
            await self._api.async_set_room_state(room_id, API_MODE_HOME)
            if room_id in overrides:
                overrides.pop(room_id, None)
                overrides_changed = True
            self._attr_hvac_mode = HVACMode.AUTO
            self._attr_preset_mode = PRESET_SCHEDULE
        elif hvac_mode == HVACMode.HEAT:
            temp = float(self.target_temperature or 20.0)
            manual_duration = self._get_option(CONF_MANUAL_DURATION, DEFAULT_MANUAL_DURATION)
            await self._api.async_set_room_state(
                room_id, API_MODE_MANUAL, temp, manual_duration
            )
            now_ts = int(time.time())
            end_ts = now_ts + manual_duration * 60
            overrides[room_id] = {
                "mode": API_MODE_MANUAL,
                "temp": temp,
                "end": end_ts,
                "sticky": True,
                "last_reapply": now_ts,
            }
            overrides_changed = True
            self._schedule_end_refresh(end_ts)
            self._attr_hvac_mode = HVACMode.HEAT
            self._attr_preset_mode = None

        # Persist overrides to storage
        if overrides_changed:
            save_overrides = self._get_save_overrides()
            if save_overrides:
                await save_overrides()

        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        room_id = self._get_room().id
        overrides = self._get_overrides()
        overrides_changed = False

        if preset_mode == PRESET_SCHEDULE:
            await self._api.async_set_room_state(room_id, API_MODE_HOME)
            self._attr_hvac_mode = HVACMode.AUTO
            if room_id in overrides:
                overrides.pop(room_id, None)
                overrides_changed = True
        elif preset_mode == PRESET_AWAY:
            away_temp = self._get_option(CONF_AWAY_TEMP, DEFAULT_AWAY_TEMP)
            away_duration = self._get_option(CONF_AWAY_DURATION, DEFAULT_AWAY_DURATION)
            await self._api.async_set_room_state(
                room_id,
                API_MODE_AWAY,
                away_temp,
                away_duration,
            )
            self._attr_hvac_mode = HVACMode.AUTO
            now_ts = int(time.time())
            end_ts = now_ts + away_duration * 60
            overrides[room_id] = {
                "mode": API_MODE_AWAY,
                "temp": float(away_temp),
                "end": end_ts,
                "sticky": True,
                "last_reapply": now_ts,
            }
            overrides_changed = True
            self._schedule_end_refresh(end_ts)
        elif preset_mode == PRESET_BOOST:
            boost_temp = self._get_option(CONF_BOOST_TEMP, DEFAULT_BOOST_TEMP)
            boost_duration = self._get_option(CONF_BOOST_DURATION, DEFAULT_BOOST_DURATION)
            await self._api.async_set_room_state(
                room_id,
                API_MODE_BOOST,
                boost_temp,
                boost_duration,
            )
            self._attr_hvac_mode = HVACMode.HEAT
            now_ts = int(time.time())
            end_ts = now_ts + boost_duration * 60
            overrides[room_id] = {
                "mode": API_MODE_BOOST,
                "temp": float(boost_temp),
                "end": end_ts,
                "sticky": True,
                "last_reapply": now_ts,
            }
            overrides_changed = True
            self._schedule_end_refresh(end_ts)
        elif preset_mode == PRESET_FROST_PROTECT:
            frost_protect_temp = self._get_option(CONF_FROST_PROTECT_TEMP, DEFAULT_FROST_PROTECT_TEMP)
            frost_protect_duration = self._get_option(CONF_FROST_PROTECT_DURATION, DEFAULT_FROST_PROTECT_DURATION)
            await self._api.async_set_room_state(
                room_id,
                API_MODE_HG,
                frost_protect_temp,
                frost_protect_duration,
            )
            self._attr_hvac_mode = HVACMode.AUTO
            now_ts = int(time.time())
            end_ts = now_ts + frost_protect_duration * 60
            overrides[room_id] = {
                "mode": API_MODE_HG,
                "temp": float(frost_protect_temp),
                "end": end_ts,
                "sticky": True,
                "last_reapply": now_ts,
            }
            overrides_changed = True
            self._schedule_end_refresh(end_ts)

        # Persist overrides to storage
        if overrides_changed:
            save_overrides = self._get_save_overrides()
            if save_overrides:
                await save_overrides()

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
            IntuisConnectClimate(coordinator, home_id, rooms.get(room_id), api, entry.entry_id)
        )
    async_add_entities(entities, update_before_add=True)
