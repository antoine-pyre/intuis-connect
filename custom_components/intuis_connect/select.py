"""Select platform for Intuis Connect."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .entity.intuis_entity import IntuisDataUpdateCoordinator
from .entity.intuis_schedule import IntuisSchedule, IntuisThermSchedule
from .intuis_api.api import IntuisAPI, APIError, CannotConnect, RateLimitError
from .utils.const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Intuis Connect select entities from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: IntuisDataUpdateCoordinator = data["coordinator"]
    api: IntuisAPI = data["api"]
    intuis_home = data["intuis_home"]

    entities: list[SelectEntity] = []

    # Add schedule selector if there are thermostat schedules
    therm_schedules = [s for s in intuis_home.schedules if isinstance(s, IntuisThermSchedule)]
    if therm_schedules:
        entities.append(
            IntuisScheduleSelect(coordinator, api, intuis_home.id, therm_schedules)
        )

    async_add_entities(entities, update_before_add=True)


class IntuisScheduleSelect(CoordinatorEntity[IntuisDataUpdateCoordinator], SelectEntity):
    """Select entity to switch between Intuis schedules."""

    _attr_icon = "mdi:calendar-clock"
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: IntuisDataUpdateCoordinator,
        api: IntuisAPI,
        home_id: str,
        schedules: list[IntuisThermSchedule],
    ) -> None:
        """Initialize the schedule select entity."""
        super().__init__(coordinator)
        self._api = api
        self._home_id = home_id
        self._schedules = schedules

        # Build schedule name to ID mapping
        self._schedule_map: dict[str, str] = {}
        self._id_to_name: dict[str, str] = {}
        for schedule in schedules:
            name = schedule.name or f"Schedule {schedule.id}"
            self._schedule_map[name] = schedule.id
            self._id_to_name[schedule.id] = name

        self._attr_unique_id = f"intuis_{home_id}_schedule_select"
        self._attr_name = "Active Schedule"
        self._attr_options = list(self._schedule_map.keys())

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the home."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._home_id}_home")},
            name="Intuis Home",
            manufacturer="Muller Intuitiv (Netatmo)",
            model="Home Controller",
        )

    @property
    def current_option(self) -> str | None:
        """Return the currently selected schedule."""
        # Find the selected schedule from coordinator data
        intuis_home = self.coordinator.data.get("intuis_home")
        if intuis_home:
            for schedule in intuis_home.schedules:
                if isinstance(schedule, IntuisThermSchedule) and schedule.selected:
                    return self._id_to_name.get(schedule.id)
        # Fallback to stored schedules
        for schedule in self._schedules:
            if schedule.selected:
                return self._id_to_name.get(schedule.id)
        return None

    async def async_select_option(self, option: str) -> None:
        """Change the selected schedule."""
        schedule_id = self._schedule_map.get(option)
        if not schedule_id:
            _LOGGER.error("Unknown schedule option: %s", option)
            return

        _LOGGER.info("Switching to schedule: %s (ID: %s)", option, schedule_id)

        try:
            await self._api.async_switch_schedule(self._home_id, schedule_id)
        except (APIError, CannotConnect, RateLimitError) as err:
            _LOGGER.error("Failed to switch schedule: %s", err)
            raise

        # Update local state
        for schedule in self._schedules:
            schedule.selected = (schedule.id == schedule_id)

        await self.coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # Update schedules from coordinator if available
        intuis_home = self.coordinator.data.get("intuis_home")
        if intuis_home:
            self._schedules = [
                s for s in intuis_home.schedules
                if isinstance(s, IntuisThermSchedule)
            ]
            # Rebuild mappings
            self._schedule_map.clear()
            self._id_to_name.clear()
            for schedule in self._schedules:
                name = schedule.name or f"Schedule {schedule.id}"
                self._schedule_map[name] = schedule.id
                self._id_to_name[schedule.id] = name
            self._attr_options = list(self._schedule_map.keys())

        self.async_write_ha_state()
