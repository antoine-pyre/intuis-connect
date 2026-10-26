"""Number platform for Intuis Connect zone temperatures."""
from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberDeviceClass, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .entity.intuis_entity import IntuisDataUpdateCoordinator
from .entity.intuis_schedule import (
    IntuisThermSchedule,
    IntuisThermZone,
    IntuisRoomTemperature,
)
from .intuis_api.api import IntuisAPI
from .schedule_mutations import async_set_zone_temperature
from .utils.const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Intuis Connect number entities from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: IntuisDataUpdateCoordinator = data["coordinator"]
    api: IntuisAPI = data["api"]
    intuis_home = data["intuis_home"]

    # Track current entities for dynamic management
    current_entity_ids: set[str] = set()

    def _build_entities() -> list[IntuisZoneTemperatureNumber]:
        """Build list of entities from current schedule data."""
        entities: list[IntuisZoneTemperatureNumber] = []

        for schedule in intuis_home.schedules:
            if not isinstance(schedule, IntuisThermSchedule):
                continue

            # Only include schedules that have zones and timetables
            if not schedule.zones or not schedule.timetables:
                continue

            for zone in schedule.zones:
                if not isinstance(zone, IntuisThermZone):
                    continue

                for room_temp in zone.rooms_temp:
                    # Get room name from home.rooms
                    room_def = intuis_home.rooms.get(room_temp.room_id)
                    room_name = room_def.name if room_def and hasattr(room_def, 'name') else f"Room {room_temp.room_id}"

                    entity = IntuisZoneTemperatureNumber(
                        coordinator=coordinator,
                        api=api,
                        home_id=intuis_home.id,
                        schedule=schedule,
                        zone=zone,
                        room_temp=room_temp,
                        room_name=room_name,
                    )
                    entities.append(entity)
                    current_entity_ids.add(entity.unique_id)

        return entities

    # Initial entity setup
    entities = _build_entities()
    _LOGGER.info("Setting up %d zone temperature number entities", len(entities))
    async_add_entities(entities, update_before_add=True)

    # Store reference for dynamic updates
    data["number_entity_ids"] = current_entity_ids
    data["number_async_add_entities"] = async_add_entities

    @callback
    def async_check_entities() -> None:
        """Check for new/removed schedules and update entities accordingly."""
        entity_registry = er.async_get(hass)
        intuis_home_current = coordinator.data.get("intuis_home")

        if not intuis_home_current:
            return

        # Build set of expected entity unique IDs
        expected_ids: set[str] = set()
        for schedule in intuis_home_current.schedules:
            if not isinstance(schedule, IntuisThermSchedule):
                continue
            if not schedule.zones or not schedule.timetables:
                continue

            for zone in schedule.zones:
                if not isinstance(zone, IntuisThermZone):
                    continue
                for room_temp in zone.rooms_temp:
                    unique_id = f"intuis_{intuis_home_current.id}_{schedule.id}_{zone.id}_{room_temp.room_id}_zone_temp"
                    expected_ids.add(unique_id)

        stored_ids: set[str] = data.get("number_entity_ids", set())

        # Find entities to remove (in stored but not in expected)
        to_remove = stored_ids - expected_ids
        for unique_id in to_remove:
            entity_id = entity_registry.async_get_entity_id("number", DOMAIN, unique_id)
            if entity_id:
                _LOGGER.info("Removing stale zone temperature entity: %s", entity_id)
                entity_registry.async_remove(entity_id)

        # Find entities to add (in expected but not in stored)
        to_add = expected_ids - stored_ids
        if to_add:
            new_entities: list[IntuisZoneTemperatureNumber] = []
            for schedule in intuis_home_current.schedules:
                if not isinstance(schedule, IntuisThermSchedule):
                    continue
                if not schedule.zones or not schedule.timetables:
                    continue

                for zone in schedule.zones:
                    if not isinstance(zone, IntuisThermZone):
                        continue
                    for room_temp in zone.rooms_temp:
                        unique_id = f"intuis_{intuis_home_current.id}_{schedule.id}_{zone.id}_{room_temp.room_id}_zone_temp"
                        if unique_id in to_add:
                            room_def = intuis_home_current.rooms.get(room_temp.room_id)
                            room_name = room_def.name if room_def and hasattr(room_def, 'name') else f"Room {room_temp.room_id}"

                            entity = IntuisZoneTemperatureNumber(
                                coordinator=coordinator,
                                api=api,
                                home_id=intuis_home_current.id,
                                schedule=schedule,
                                zone=zone,
                                room_temp=room_temp,
                                room_name=room_name,
                            )
                            new_entities.append(entity)
                            _LOGGER.info("Adding new zone temperature entity: %s", unique_id)

            if new_entities:
                add_entities_callback = data.get("number_async_add_entities")
                if add_entities_callback:
                    add_entities_callback(new_entities, update_before_add=True)

        # Update stored IDs
        data["number_entity_ids"] = expected_ids

    # Register listener for coordinator updates
    entry.async_on_unload(
        coordinator.async_add_listener(async_check_entities)
    )


class IntuisZoneTemperatureNumber(CoordinatorEntity[IntuisDataUpdateCoordinator], NumberEntity):
    """Number entity to edit zone temperature for a specific room."""

    _attr_native_min_value = 5.0
    _attr_native_max_value = 30.0
    _attr_native_step = 0.5
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:thermometer"
    _attr_has_entity_name = True
    _attr_entity_registry_enabled_default = False  # Disabled by default to avoid entity explosion

    def __init__(
        self,
        coordinator: IntuisDataUpdateCoordinator,
        api: IntuisAPI,
        home_id: str,
        schedule: IntuisThermSchedule,
        zone: IntuisThermZone,
        room_temp: IntuisRoomTemperature,
        room_name: str,
    ) -> None:
        """Initialize the zone temperature number entity."""
        super().__init__(coordinator)
        self._api = api
        self._home_id = home_id
        self._schedule_id = schedule.id
        self._schedule_name = schedule.name
        self._zone_id = zone.id
        self._zone_name = zone.name
        self._room_id = room_temp.room_id
        self._room_name = room_name
        self._cached_temp = float(room_temp.temp)

        # Unique ID
        self._attr_unique_id = f"intuis_{home_id}_{schedule.id}_{zone.id}_{room_temp.room_id}_zone_temp"

        # Entity name: just zone + room since schedule is the device
        self._attr_name = f"{zone.name} {room_name}"

    @property
    def unique_id(self) -> str:
        """Return the unique ID."""
        return self._attr_unique_id

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info - grouped by schedule."""
        home = self.coordinator.data.get("intuis_home")
        schedule = next((s for s in home.schedules if s.id == self._schedule_id), None) if home else None
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._home_id}_schedule_{self._schedule_id}")},
            name=f"Schedule {schedule.name if schedule else self._schedule_name}",
            manufacturer="Muller Intuitiv (Netatmo)",
            model="Heating Schedule",
            via_device=(DOMAIN, f"{self._home_id}_home"),
        )

    @property
    def native_value(self) -> float | None:
        """Return the current temperature setting."""
        intuis_home = self.coordinator.data.get("intuis_home")
        if not intuis_home:
            return self._cached_temp

        # Navigate to the specific rooms_temp entry
        for schedule in intuis_home.schedules:
            if not isinstance(schedule, IntuisThermSchedule):
                continue
            if schedule.id != self._schedule_id:
                continue
            for zone in schedule.zones:
                if not isinstance(zone, IntuisThermZone):
                    continue
                if zone.id != self._zone_id:
                    continue
                for room_temp in zone.rooms_temp:
                    if room_temp.room_id == self._room_id:
                        self._cached_temp = float(room_temp.temp)
                        return self._cached_temp

        return self._cached_temp

    async def async_set_native_value(self, value: float) -> None:
        """Preserve half degrees and publish only after a confirmed cloud write."""
        try:
            await async_set_zone_temperature(
                self._api, lambda: self.coordinator.data["intuis_home"],
                self._schedule_id, self._room_id, value, zone_id=self._zone_id,
            )
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        self._cached_temp = float(value)
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        from homeassistant.helpers import device_registry as dr
        registry = dr.async_get(self.hass)
        if hasattr(registry, "async_get_devices"):
            devices = registry.async_get_devices(identifiers=self.device_info["identifiers"])
        else:
            device = registry.async_get_device(identifiers=self.device_info["identifiers"])
            devices = [device] if device else []
        for device in devices:
            if device.name != self.device_info["name"]:
                registry.async_update_device(device.id, name=self.device_info["name"])
        # Update cached value from coordinator if available
        intuis_home = self.coordinator.data.get("intuis_home")
        if intuis_home:
            for schedule in intuis_home.schedules:
                if not isinstance(schedule, IntuisThermSchedule):
                    continue
                if schedule.id != self._schedule_id:
                    continue
                for zone in schedule.zones:
                    if not isinstance(zone, IntuisThermZone):
                        continue
                    if zone.id != self._zone_id:
                        continue
                    for room_temp in zone.rooms_temp:
                        if room_temp.room_id == self._room_id:
                            self._cached_temp = float(room_temp.temp)
                            break
                    break
                break

        self.async_write_ha_state()
