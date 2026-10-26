"""Climate platform for Intuis Connect."""

from __future__ import annotations

import logging
import time
from typing import Any
from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.core import callback

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
from .overrides import OverrideIntent, OverrideManager, OverrideState
from .entity.intuis_room import IntuisRoom
from .utils.const import (
    PRESET_AWAY,
    PRESET_BOOST,
    PRESET_SCHEDULE,
    PRESET_FROST_PROTECT,
    API_MODE_OFF,
    API_MODE_AUTO,
    API_MODE_MANUAL,
    API_MODE_AWAY,
    API_MODE_BOOST,
    API_MODE_HG,
    API_MODE_HOME,
    DEFAULT_AWAY_TEMP,
    DEFAULT_AWAY_DURATION,
    DEFAULT_BOOST_TEMP,
    DEFAULT_BOOST_DURATION,
    DEFAULT_FROST_PROTECT_TEMP,
    DEFAULT_FROST_PROTECT_DURATION,
    DEFAULT_MANUAL_DURATION,
    DOMAIN,
    CONF_MANUAL_DURATION,
    CONF_AWAY_DURATION,
    CONF_BOOST_DURATION,
    CONF_FROST_PROTECT_DURATION,
    CONF_AWAY_TEMP,
    CONF_BOOST_TEMP,
    CONF_FROST_PROTECT_TEMP,
)
from .entity.intuis_entity import IntuisEntity, IntuisDataUpdateCoordinator
from .utils.helper import get_basic_utils

_LOGGER = logging.getLogger(__name__)


# A pending command is a short-lived display hint, never a persisted state.
OPTIMISTIC_TIMEOUT = 120


@dataclass(frozen=True)
class PendingCommand:
    api_mode: str
    temperature: float | None
    hvac_mode: HVACMode
    preset_mode: str | None
    deadline: float
    end_ts: int | None = None


class IntuisConnectClimate(
    CoordinatorEntity[IntuisDataUpdateCoordinator], ClimateEntity, IntuisEntity
):
    """Climate entity for an Intuis Connect-compatible device."""

    _attr_hvac_modes = [HVACMode.AUTO, HVACMode.HEAT, HVACMode.OFF]
    _attr_preset_modes = [
        PRESET_AWAY,
        PRESET_BOOST,
        PRESET_SCHEDULE,
        PRESET_FROST_PROTECT,
    ]
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
        IntuisEntity.__init__(
            self, coordinator, room, home_id, f"{room.name} Climate", "climate"
        )
        self._home_id = home_id
        self._api = api
        self._entry_id = entry_id
        self._attr_assumed_state = False
        self._attr_hvac_mode = None
        self._attr_preset_mode = None
        self._attr_target_temperature = None
        self._pending: PendingCommand | None = None
        self._cancel_pending: Callable[[], None] | None = None
        self._cancel_end: Callable[[], None] | None = None
        self._removed = False
        self._scheduled_end_ts: int | None = None

    def _get_override_manager(self) -> OverrideManager:
        data = self.hass.data[DOMAIN][self._entry_id]
        manager = data.get("override_manager")
        if manager is None:
            manager = data["override_manager"] = OverrideManager(
                data.setdefault("overrides", {}),
                data.get("save_overrides"),
            )
        return manager

    def _get_overrides(self) -> OverrideState:
        if self._entry_id not in self.hass.data.get(DOMAIN, {}):
            return {}
        return self._get_override_manager().overrides

    def _get_option(self, key: str, default: Any) -> Any:
        """Get an option value from the config entry."""
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        if entry:
            return entry.options.get(key, default)
        return default

    def _cancel_timer(self, name: str) -> None:
        cancel = getattr(self, name)
        if cancel is not None:
            cancel()
            setattr(self, name, None)

    def _clear_pending(self) -> None:
        self._cancel_timer("_cancel_pending")
        self._pending = None
        self._attr_hvac_mode = self._attr_preset_mode = (
            self._attr_target_temperature
        ) = None
        self._attr_assumed_state = False

    def _active_pending(self) -> PendingCommand | None:
        if self._pending is not None and time.monotonic() >= self._pending.deadline:
            self._clear_pending()
        return self._pending

    def _schedule_end_refresh(self, end_ts: int) -> None:
        self._cancel_timer("_cancel_end")
        self._scheduled_end_ts = end_ts

        async def expired(_now):
            self._cancel_end = None
            self._scheduled_end_ts = None
            if self._removed:
                return
            self._clear_pending()
            self.async_write_ha_state()
            await self.coordinator.async_request_refresh()

        self._cancel_end = async_call_later(
            self.hass,
            max(0, end_ts - int(time.time()) + 1),
            expired,
        )

    def _publish_pending(
        self,
        mode: str,
        temperature: float | None,
        hvac: HVACMode,
        preset: str | None,
        intent: OverrideIntent | None,
    ) -> None:
        if self._removed:
            return
        self._clear_pending()
        self._cancel_timer("_cancel_end")
        self._pending = PendingCommand(
            mode,
            temperature,
            hvac,
            preset,
            time.monotonic() + OPTIMISTIC_TIMEOUT,
            intent["end"] if intent is not None else None,
        )
        self._attr_hvac_mode, self._attr_preset_mode = hvac, preset
        self._attr_target_temperature = temperature
        self._attr_assumed_state = True

        @callback
        def expire_pending(_now):
            self._cancel_pending = None
            if not self._removed:
                self._clear_pending()
                # State clears even if cloud refreshes fail. The normal poll
                # remains responsible for fetching data; this deadline is local.
                self.async_write_ha_state()

        self._cancel_pending = async_call_later(
            self.hass, OPTIMISTIC_TIMEOUT, expire_pending
        )
        if intent is not None:
            self._schedule_end_refresh(intent["end"])
        self.async_write_ha_state()

    @staticmethod
    def _observes_command(
        room: IntuisRoom,
        mode: str,
        temperature: float | None,
        end_ts: int | None = None,
    ) -> bool:
        observed_end = getattr(room, "therm_setpoint_end_time", None)
        if (
            end_ts is not None
            and isinstance(observed_end, (int, float))
            and observed_end > 0
            and abs(observed_end - end_ts) > 60
        ):
            return False
        if mode == API_MODE_HOME:
            return (
                room.mode in (API_MODE_AUTO, API_MODE_HOME)
                and room.boost_status != "in_progress"
            )
        if mode == API_MODE_BOOST and room.boost_status == "in_progress":
            return True
        try:
            same_temperature = (
                temperature is not None
                and abs(float(room.target_temperature) - float(temperature)) < 0.01
            )
        except (TypeError, ValueError):
            same_temperature = False
        if room.mode == mode:
            return temperature is None or same_temperature
        # Intuis often exposes away/hg/boost as a manual temperature override.
        return (
            mode in (API_MODE_AWAY, API_MODE_HG, API_MODE_BOOST)
            and room.mode == API_MODE_MANUAL
            and temperature is not None
            and same_temperature
        )

    def _observed_override(self) -> OverrideIntent | None:
        room = self._get_room()
        if room is None:
            return None
        intent = self._get_overrides().get(room.id)
        if intent is None:
            return None
        try:
            active = int(intent.get("end", 0)) > int(time.time())
        except (ValueError, TypeError):
            return None
        if active and self._observes_command(
            room, intent.get("mode"), intent.get("temp"), intent.get("end")
        ):
            return intent
        return None

    @callback
    def _handle_coordinator_update(self) -> None:
        pending = self._active_pending()
        room = self._get_room()
        if (
            self.coordinator.last_update_success
            and room is not None
            and pending is not None
            and self._observes_command(
                room, pending.api_mode, pending.temperature, pending.end_ts
            )
        ):
            self._clear_pending()
        if self.coordinator.last_update_success and not self._removed:
            intent = self._get_overrides().get(self._room.id)
            try:
                end = int(intent["end"]) if intent is not None else 0
            except (KeyError, ValueError, TypeError):
                end = 0
            if end > int(time.time()) and end != self._scheduled_end_ts:
                self._schedule_end_refresh(end)
            elif end <= int(time.time()):
                self._cancel_timer("_cancel_end")
                self._scheduled_end_ts = None
        super()._handle_coordinator_update()

    async def async_will_remove_from_hass(self) -> None:
        self._removed = True
        self._clear_pending()
        self._cancel_timer("_cancel_end")
        self._scheduled_end_ts = None
        await super().async_will_remove_from_hass()

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return self._attr_device_info

    @property
    def current_temperature(self) -> StateType:
        room = self._get_room()
        return room.temperature if room is not None else None

    @property
    def target_temperature(self) -> StateType:
        pending = self._active_pending()
        if pending is not None and pending.temperature is not None:
            return pending.temperature
        room = self._get_room()
        return room.target_temperature if room is not None else None

    @property
    def hvac_mode(self) -> HVACMode | None:
        pending = self._active_pending()
        if pending is not None:
            return pending.hvac_mode
        room = self._get_room()
        if room is None:
            return None
        if self._is_boost_active():
            return HVACMode.HEAT
        if room.mode == API_MODE_OFF:
            return HVACMode.OFF
        intent = self._observed_override()
        if intent is not None and intent["mode"] in (API_MODE_AWAY, API_MODE_HG):
            return HVACMode.AUTO
        if room.mode in (API_MODE_AUTO, API_MODE_AWAY, API_MODE_HOME, API_MODE_HG):
            return HVACMode.AUTO
        return HVACMode.HEAT

    @property
    def preset_mode(self) -> str | None:
        pending = self._active_pending()
        if pending is not None:
            return pending.preset_mode
        room = self._get_room()
        if room is None:
            return None
        if room.boost_status == "in_progress":
            return PRESET_BOOST
        intent = self._observed_override()
        mode = intent["mode"] if intent is not None else room.mode
        preset = {
            API_MODE_AWAY: PRESET_AWAY,
            API_MODE_BOOST: PRESET_BOOST,
            API_MODE_HG: PRESET_FROST_PROTECT,
        }.get(mode)
        if preset is not None:
            return preset
        return PRESET_SCHEDULE if self.hvac_mode == HVACMode.AUTO else None

    def _is_boost_active(self) -> bool:
        room = self._get_room()
        if room is None:
            return False
        # A persisted intent alone never proves that the equipment is heating.
        return room.boost_status == "in_progress" or room.mode == API_MODE_BOOST

    @property
    def hvac_action(self) -> HVACAction | None:
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        room = self._get_room()
        if room is None:
            return HVACAction.IDLE
        return (
            HVACAction.HEATING
            if room.heating or self._is_boost_active()
            else HVACAction.IDLE
        )

    async def _async_command(
        self,
        mode: str,
        hvac: HVACMode,
        preset: str | None,
        temperature: float | None = None,
        duration: int | None = None,
    ) -> None:
        room = self._get_room()
        if self._removed or room is None:
            raise ValueError("Room is unavailable")
        await self._get_override_manager().async_command(
            self._api,
            room.id,
            mode,
            temperature,
            duration,
            on_success=lambda intent: self._publish_pending(
                mode, temperature, hvac, preset, intent
            ),
        )
        if not self._removed:
            await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = kwargs.get("temperature")
        if temperature is not None:
            await self._async_command(
                API_MODE_MANUAL,
                HVACMode.HEAT,
                None,
                float(temperature),
                self._get_option(CONF_MANUAL_DURATION, DEFAULT_MANUAL_DURATION),
            )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self._async_command(API_MODE_OFF, HVACMode.OFF, None)
        elif hvac_mode == HVACMode.AUTO:
            await self._async_command(API_MODE_HOME, HVACMode.AUTO, PRESET_SCHEDULE)
        elif hvac_mode == HVACMode.HEAT:
            await self._async_command(
                API_MODE_MANUAL,
                HVACMode.HEAT,
                None,
                float(self.target_temperature or 20.0),
                self._get_option(CONF_MANUAL_DURATION, DEFAULT_MANUAL_DURATION),
            )
        else:
            raise ValueError(f"Unsupported HVAC mode: {hvac_mode}")

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        if preset_mode == PRESET_SCHEDULE:
            await self._async_command(API_MODE_HOME, HVACMode.AUTO, PRESET_SCHEDULE)
            return
        settings = {
            PRESET_AWAY: (
                API_MODE_AWAY,
                HVACMode.AUTO,
                CONF_AWAY_TEMP,
                DEFAULT_AWAY_TEMP,
                CONF_AWAY_DURATION,
                DEFAULT_AWAY_DURATION,
            ),
            PRESET_BOOST: (
                API_MODE_BOOST,
                HVACMode.HEAT,
                CONF_BOOST_TEMP,
                DEFAULT_BOOST_TEMP,
                CONF_BOOST_DURATION,
                DEFAULT_BOOST_DURATION,
            ),
            PRESET_FROST_PROTECT: (
                API_MODE_HG,
                HVACMode.AUTO,
                CONF_FROST_PROTECT_TEMP,
                DEFAULT_FROST_PROTECT_TEMP,
                CONF_FROST_PROTECT_DURATION,
                DEFAULT_FROST_PROTECT_DURATION,
            ),
        }
        if preset_mode not in settings:
            raise ValueError(f"Unsupported preset: {preset_mode}")
        mode, hvac, temp_key, temp_default, duration_key, duration_default = settings[
            preset_mode
        ]
        await self._async_command(
            mode,
            hvac,
            preset_mode,
            self._get_option(temp_key, temp_default),
            self._get_option(duration_key, duration_default),
        )


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the climate entities."""
    coordinator, home_id, rooms, api = get_basic_utils(hass, entry)

    entities = []
    for room_id in rooms:
        entities.append(
            IntuisConnectClimate(
                coordinator, home_id, rooms.get(room_id), api, entry.entry_id
            )
        )
    async_add_entities(entities, update_before_add=True)
