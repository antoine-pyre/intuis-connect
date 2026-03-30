"""Sensor platform for Intuis Connect."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

import homeassistant.util.dt as dt_util
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfTemperature, UnitOfEnergy, EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .entity.intuis_entity import IntuisEntity
from .entity.intuis_home_entity import provide_home_sensors
from .entity.intuis_module import NMHIntuisModule, NMRIntuisModule, IntuisModule
from .entity.intuis_room import IntuisRoom
from .entity.intuis_schedule import IntuisThermSchedule, IntuisThermZone
from .timetable import MINUTES_PER_DAY
from .utils.const import (
    DOMAIN,
    CONF_ENERGY_COST_ENABLED,
    DEFAULT_ENERGY_COST_ENABLED,
)
from .utils.helper import get_basic_utils

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Intuis Connect sensors from a config entry."""
    coordinator, home_id, rooms, api = get_basic_utils(hass, entry)
    intuis_home = hass.data[DOMAIN][entry.entry_id].get("intuis_home")

    entities: list[SensorEntity] = []
    for room_id in rooms:
        room = rooms.get(room_id)
        entities.append(IntuisTemperatureSensor(coordinator, home_id, room))
        entities.append(IntuisMullerTypeSensor(coordinator, home_id, room))
        entities.append(IntuisEnergySensor(coordinator, home_id, room))
        # Add cost sensor if enabled
        if entry.options.get(CONF_ENERGY_COST_ENABLED, DEFAULT_ENERGY_COST_ENABLED):
            entities.append(IntuisEnergyCostSensor(coordinator, home_id, room))
        entities.append(IntuisMinutesSensor(coordinator, home_id, room))
        entities.append(IntuisSetpointEndTimeSensor(coordinator, home_id, room))
        entities.append(IntuisScheduledTempSensor(coordinator, home_id, room, intuis_home))

        # Add module sensors for each NMH module
        for module in room.modules:
            if isinstance(module, NMHIntuisModule):
                entities.append(ModuleLastSeenSensor(coordinator, home_id, room, module))
                entities.append(ModuleFirmwareSensor(coordinator, home_id, room, module))

    entities += provide_home_sensors(coordinator, home_id, intuis_home)
    
    # Add schedule data sensor for UI integration (summary only)
    # Note: Individual schedule sensors are created in provide_home_sensors
    # via IntuisScheduleSummarySensor to avoid duplicate entity IDs
    if intuis_home and intuis_home.schedules:
        entities.append(IntuisScheduleDataSensor(coordinator, home_id, intuis_home))
    
    async_add_entities(entities, update_before_add=True)


class IntuisSensor(CoordinatorEntity, SensorEntity, IntuisEntity):
    """Generic sensor for an Intuis Connect room metric."""

    def __init__(
            self,
            coordinator,
            home_id: str,
            room: IntuisRoom,
            metric: str,
            label: str,
            unit: str | None,
            device_class: str | None,
    ) -> None:
        """Initialize the sensor."""
        CoordinatorEntity.__init__(self, coordinator)
        SensorEntity.__init__(self)
        IntuisEntity.__init__(self, coordinator, room, home_id, f"{room.name} {label}", metric)

        self._metric = metric
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator.

        The Intuis coordinator rebuilds IntuisRoom objects on each refresh.
        Keep our internal room reference in sync so any remaining usages of
        ``self._room`` don't end up stuck on the initial instance.
        """
        room = self._get_room()
        if room is not None:
            self._room = room
        super()._handle_coordinator_update()

    @property
    def native_value(self) -> float | int | None:
        """Return the current value of this sensor."""
        raise NotImplementedError(
            f"Subclasses of IntuisSensor must implement native_value for {self._metric}"
        )


class IntuisMullerTypeSensor(IntuisSensor):
    """Specialized sensor for device type."""

    def __init__(self, coordinator, home_id: str, room: IntuisRoom) -> None:
        """Initialize the muller type sensor."""
        super().__init__(
            coordinator,
            home_id,
            room,
            "muller_type",
            "Device Type",
            unit=None,
            device_class=None,
        )
        self._attr_icon = "mdi:device-hub"
        self._attr_available = False
        self._attr_entity_registry_enabled_default = False

    @property
    def native_value(self) -> str:
        """Return the current device type."""
        # Ensure we handle None values gracefully
        room = self._get_room() or self._room
        muller_type = room.muller_type
        if muller_type is None:
            return ""
        return muller_type


class IntuisTemperatureSensor(IntuisSensor):
    """Specialized sensor for temperature data."""

    def __init__(self, coordinator, home_id: str, room: IntuisRoom) -> None:
        """Initialize the temperature sensor."""
        super().__init__(
            coordinator,
            home_id,
            room,
            "temperature",
            "Temperature",
            UnitOfTemperature.CELSIUS,
            "temperature",
        )
        self._attr_icon = "mdi:thermometer"
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float:
        """Return the current temperature value."""
        # Ensure we handle None values gracefully
        room = self._get_room() or self._room
        temperature = room.temperature
        if temperature is None:
            return 0.0
        return temperature


class IntuisMinutesSensor(IntuisSensor):
    """Specialized sensor for heating minutes."""

    def __init__(self, coordinator, home_id: str, room: IntuisRoom) -> None:
        """Initialize the minutes sensor."""
        super().__init__(
            coordinator,
            home_id,
            room,
            "minutes",
            "Heating Minutes",
            "min",
            None,
        )
        self._attr_icon = "mdi:timer"
        # tell HA this is a duration sensor
        self._attr_device_class = SensorDeviceClass.DURATION
        # treat it like a measurement (so it will chart properly)
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_entity_registry_enabled_default = False

    @property
    def native_value(self) -> int:
        """Return the current heating minutes value."""
        # Ensure we handle None values gracefully
        room = self._get_room() or self._room
        minutes = room.minutes
        if minutes is None:
            return 0
        return minutes


class IntuisEnergySensor(IntuisSensor):
    """Sensor exposing the cumulative total energy consumption.

    Mirrors the Node-RED sensor.conso_X_hourly behavior:
      native_value = base_kwh + daily_energy
    where base_kwh is the cumulative total at the start of today (from
    hourly_stats persistent storage), and daily_energy is the current
    day's consumption from the Intuis API.

    NO state_class: hourly_stats is the sole writer of statistics via
    recorder.async_import_statistics.  The recorder must NOT auto-generate
    competing LTS from sensor states (state_class would cause double-writing
    since both the recorder STS→LTS compilation and hourly_stats import with
    source="recorder" would write to the same statistics row, causing
    cumulative sum corruption on every HA restart).
    """

    def __init__(self, coordinator, home_id: str, room: IntuisRoom) -> None:
        """Initialize the energy sensor."""
        super().__init__(
            coordinator,
            home_id,
            room,
            "energy",
            "Energy",
            UnitOfEnergy.KILO_WATT_HOUR,
            SensorDeviceClass.ENERGY,
        )
        self._attr_icon = "mdi:flash"
        # NO state_class intentionally: hourly_stats is the sole writer of
        # sum statistics via async_import_statistics. Any state_class causes
        # either double-writing (TOTAL_INCREASING) or dashboard warnings
        # (MEASUREMENT needs last_reset). Spook warnings can be ignored.

        # Track daily max to prevent API glitch causing decreases
        self._daily_max_energy: float = 0.0
        self._last_logical_day: str | None = None

    def _get_base_kwh(self) -> float | None:
        """Read sensor_base for this entity from hourly_stats shared data.

        sensor_base = cumulative sum at TODAY midnight (00:00 local)
        Published by hourly_stats into hass.data[DOMAIN]["sensor_base"]

        Returns None if not yet published (startup: hourly_stats not yet
        initialized). native_value returns None in that case so the sensor
        stays unavailable rather than briefly showing 0 + daily_energy.
        """
        try:
            if not self.hass or not self.entity_id:
                return None
            base_all = self.hass.data.get(DOMAIN, {}).get("sensor_base", {})
            val = base_all.get(self.entity_id)
            if val is None:
                return None  # hourly_stats not yet published
            return float(val)
        except (TypeError, ValueError, AttributeError):
            return None

    @property
    def native_value(self) -> float | None:
        """Return cumulative total energy = sensor_base + daily consumption.

        sensor_base = sum at TODAY midnight (from hourly_stats)
        daily = consumption since midnight (from API)

        Returns None (unavailable) until hourly_stats has published sensor_base,
        preventing a false low value being recorded at startup.

        At midnight (day change), the sensor self-advances sensor_base
        by adding yesterday's daily max, preventing a gap until hourly_stats
        updates sensor_base with the correct value from imported data.
        """
        room = self._get_room() or self._room
        if room is None:
            return None

        energy_val = room.energy
        if hasattr(energy_val, "energy"):
            energy_val = energy_val.energy
        # If energy_val is None the coordinator hasn't polled yet.
        # Return None (unavailable) to avoid recording sensor_base+0 as a state,
        # which would appear as a downward spike in state_history on every restart.
        if energy_val is None:
            return None
        current_energy = float(energy_val)

        # Track daily max (prevent API glitch causing decreases)
        now = dt_util.now()
        logical_day = now.date().isoformat()

        if self._last_logical_day is None:
            self._daily_max_energy = current_energy
            self._last_logical_day = logical_day
        elif self._last_logical_day != logical_day:
            # New day: self-advance sensor_base by yesterday's consumption
            # This prevents the glitch between midnight and first hourly_stats cycle
            try:
                if self.hass and self.entity_id:
                    base_all = self.hass.data.get(DOMAIN, {}).get("sensor_base", {})
                    old_base = float(base_all.get(self.entity_id, 0.0))
                    if old_base > 0 and self._daily_max_energy > 0:
                        new_base = round(old_base + self._daily_max_energy, 3)
                        base_all[self.entity_id] = new_base
                        _LOGGER.info(
                            "Midnight advance %s: sensor_base %.3f + daily %.3f = %.3f",
                            self.entity_id, old_base, self._daily_max_energy, new_base,
                        )
            except (TypeError, ValueError, AttributeError):
                pass
            # Reset daily max for new day
            self._daily_max_energy = current_energy
            self._last_logical_day = logical_day
        elif current_energy > self._daily_max_energy:
            self._daily_max_energy = current_energy

        # Cumulative total = base + daily
        # None = hourly_stats not yet ready → sensor stays unavailable
        # We wait for hourly_stats_ready flag (set after first LTS write) to avoid
        # recording a high current value that creates a spike relative to the last
        # LTS point (which can be 6h+ behind due to API data lag).
        if not self.hass.data.get(DOMAIN, {}).get("hourly_stats_ready", False):
            return None
        base = self._get_base_kwh()
        if base is None:
            return None

        return round(base + self._daily_max_energy, 3)


class IntuisEnergyCostSensor(IntuisSensor):
    """Sensor exposing cumulative energy cost.

    Mirrors IntuisEnergySensor but for cost in the configured currency.
    The state reflects the LTS cumulative cost written by CostStatsUpdater.

    Cost sensor for a single room. Written exclusively via async_import_statistics.
    cost picker (Settings > Energy > cost sensor selector).
    cost_stats writes LTS via async_import_statistics (UPSERT), which
    overwrites any recorder auto-compiled entries on each import cycle.
    """

    def __init__(self, coordinator, home_id: str, room: IntuisRoom) -> None:
        """Initialize the energy cost sensor."""
        super().__init__(
            coordinator,
            home_id,
            room,
            "cost",
            "Cost",
            unit=None,   # Set dynamically via native_unit_of_measurement
            device_class=SensorDeviceClass.MONETARY,
        )
        self._attr_icon = "mdi:cash"
        # state_class=TOTAL is required for two reasons:
        # 1. The Energy Dashboard "total cost entity" mode uses the entity
        #    state for the current partial-hour value. Without state_class,
        #    HA has no fresh "current" value and falls back to stale data.
        # 2. native_value now publishes prev_sum (lifetime cumulative, e.g.
        #    212 CHF) — the same value as the LTS sum — so short-term stats
        #    compiled by HA from entity states are CORRECT and coherent with
        #    our hourly LTS import. No more divergence.
        # Previous issue (negatives) was caused by publishing midnight_base
        # (~3 CHF) instead of lifetime cumulative — now fixed in _publish_cost_base.
        self._attr_state_class = SensorStateClass.TOTAL

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the configured currency."""
        try:
            return self.hass.config.currency or "EUR"
        except AttributeError:
            return "EUR"

    @property
    def native_value(self) -> float | None:
        """Always return None.

        The Energy Dashboard reads cost data exclusively from the LTS written
        by CostStatsUpdater via async_import_statistics (source="recorder").

        If this property returned a real value, HA's recorder would compile
        entity states into statistics_short_term, then promote them into the
        hourly Statistics table.  Because our LTS sum and the compiled sum are
        computed independently and can diverge (especially across restarts,
        recalculate runs, or timezone edge cases), HA ends up with two sets of
        rows for the same (metadata_id, start_ts) key.  The last writer wins
        and the loser creates a negative-delta spike visible in the dashboard.

        Returning None means HA never writes short-term stats for this entity,
        so async_import_statistics is the sole writer — no conflicts.

        state_class=TOTAL is still declared (on self._attr_state_class) so
        the entity appears in the Energy Dashboard "total cost" selector.
        """
        return None




class IntuisSetpointEndTimeSensor(IntuisSensor):
    """Sensor showing when the current temperature override will expire."""

    def __init__(self, coordinator, home_id: str, room: IntuisRoom) -> None:
        """Initialize the setpoint end time sensor."""
        super().__init__(
            coordinator,
            home_id,
            room,
            "setpoint_end_time",
            "Override Expires",
            unit=None,
            device_class=SensorDeviceClass.TIMESTAMP,
        )
        self._attr_icon = "mdi:timer-sand"
        self._attr_entity_registry_enabled_default = False

    @property
    def native_value(self) -> datetime | None:
        """Return the end time of the current override as a datetime."""
        room = self._get_room() or self._room
        if room is None:
            return None
        end_ts = room.therm_setpoint_end_time
        if not end_ts or end_ts == 0:
            return None
        try:
            return datetime.fromtimestamp(end_ts, tz=timezone.utc)
        except (ValueError, OSError):
            return None


class IntuisScheduledTempSensor(IntuisSensor):
    """Sensor showing the currently scheduled temperature for a room.

    This shows what temperature the room SHOULD be at according to the
    active schedule, regardless of any manual overrides.
    """

    def __init__(self, coordinator, home_id: str, room: IntuisRoom, intuis_home) -> None:
        """Initialize the scheduled temperature sensor."""
        super().__init__(
            coordinator,
            home_id,
            room,
            "scheduled_temp",
            "Scheduled Temperature",
            UnitOfTemperature.CELSIUS,
            None,
        )
        self._intuis_home = intuis_home
        self._attr_icon = "mdi:calendar-clock"
        self._attr_entity_registry_enabled_default = False

    def _get_current_zone(self) -> IntuisThermZone | None:
        """Get the currently active zone based on the time of day."""
        # Get the active schedule
        intuis_home = self.coordinator.data.get("intuis_home") or self._intuis_home
        if not intuis_home or not intuis_home.schedules:
            return None

        active_schedule = None
        for schedule in intuis_home.schedules:
            if isinstance(schedule, IntuisThermSchedule) and schedule.selected:
                active_schedule = schedule
                break

        if not active_schedule:
            return None

        # Calculate current minute offset in the week
        # m_offset: 0 = Monday 00:00, MINUTES_PER_DAY = Tuesday 00:00, etc.
        now = dt_util.now()
        # Python weekday: Monday = 0, Sunday = 6
        day_of_week = now.weekday()
        minutes_today = now.hour * 60 + now.minute
        current_offset = day_of_week * MINUTES_PER_DAY + minutes_today

        # Find the active zone for this time
        # Timetables are sorted by m_offset, find the last one <= current_offset
        active_zone_id = None
        for timetable in active_schedule.timetables:
            if timetable.m_offset <= current_offset:
                active_zone_id = timetable.zone_id

        # Handle week wrap-around: if no zone found (e.g., Monday 00:00 before first entry),
        # use the last zone from the previous week (which wraps from Sunday)
        if active_zone_id is None and active_schedule.timetables:
            active_zone_id = active_schedule.timetables[-1].zone_id

        if active_zone_id is None:
            return None

        # Find the zone object
        for zone in active_schedule.zones:
            if isinstance(zone, IntuisThermZone) and zone.id == active_zone_id:
                return zone

        return None

    @property
    def native_value(self) -> float | None:
        """Return the currently scheduled temperature for this room."""
        zone = self._get_current_zone()
        if not zone:
            return None

        # Find this room's temperature in the zone
        room = self._get_room() or self._room
        room_id = room.id if room else None
        if not room_id:
            return None

        for room_config in zone.rooms:
            if room_config.id == room_id:
                if room_config.therm_setpoint_temperature is not None:
                    return float(room_config.therm_setpoint_temperature)
                # If using preset mode, we can't determine exact temperature
                return None

        return None

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional state attributes."""
        zone = self._get_current_zone()
        attrs = {}

        if zone:
            attrs["zone_id"] = zone.id
            attrs["zone_name"] = zone.name
            attrs["zone_type"] = zone.type

            # Find room preset if any
            room = self._get_room() or self._room
            room_id = room.id if room else None
            if room_id:
                for room_config in zone.rooms:
                    if room_config.id == room_id and room_config.therm_setpoint_fp:
                        attrs["preset_mode"] = room_config.therm_setpoint_fp

        return attrs


class ModuleLastSeenSensor(IntuisSensor):
    """Sensor showing when a module was last seen."""

    def __init__(
            self,
            coordinator,
            home_id: str,
            room: IntuisRoom,
            module: NMHIntuisModule,
    ) -> None:
        self._module_id = module.id
        short_id = module.id[-6:] if len(module.id) > 6 else module.id
        super().__init__(
            coordinator,
            home_id,
            room,
            f"module_{module.id}_last_seen",
            f"{short_id} Last Seen",
            unit=None,
            device_class=SensorDeviceClass.TIMESTAMP,
        )
        self._attr_entity_registry_enabled_default = False
        self._attr_icon = "mdi:clock-outline"

    @property
    def native_value(self) -> datetime | None:
        """Return the last seen timestamp as datetime."""
        room = self._get_room()
        if not room or not room.modules:
            return None
        for module in room.modules:
            if isinstance(module, NMHIntuisModule) and module.id == self._module_id:
                if module.last_seen:
                    return datetime.fromtimestamp(module.last_seen, tz=timezone.utc)
        return None

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional attributes including stale status."""
        attrs = {}
        room = self._get_room()
        if room and room.modules:
            for module in room.modules:
                if isinstance(module, NMHIntuisModule) and module.id == self._module_id:
                    if module.last_seen:
                        age_seconds = int(datetime.now(timezone.utc).timestamp() - module.last_seen)
                        attrs["age_seconds"] = age_seconds
                        attrs["stale"] = age_seconds > 3600  # Stale if > 1 hour
        return attrs


class ModuleFirmwareSensor(IntuisSensor):
    """Sensor showing module firmware version."""

    def __init__(
            self,
            coordinator,
            home_id: str,
            room: IntuisRoom,
            module: NMHIntuisModule,
    ) -> None:
        self._module_id = module.id
        short_id = module.id[-6:] if len(module.id) > 6 else module.id
        super().__init__(
            coordinator,
            home_id,
            room,
            f"module_{module.id}_firmware",
            f"{short_id} Firmware",
            unit=None,
            device_class=None,
        )
        self._attr_entity_registry_enabled_default = False
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_icon = "mdi:chip"

    @property
    def native_value(self) -> str | None:
        """Return the firmware version."""
        room = self._get_room()
        if not room or not room.modules:
            return None
        for module in room.modules:
            if isinstance(module, NMHIntuisModule) and module.id == self._module_id:
                return module.firmware_revision_thirdparty
        return None


class IntuisScheduleDataSensor(CoordinatorEntity, SensorEntity):
    """Sensor exposing complete schedule data for UI integration.
    
    This sensor exposes the full timetable, zones, and room temperatures
    for the currently selected schedule, making it accessible to custom
    UI components like the Intuis Planning page.
    """

    def __init__(
            self,
            coordinator,
            home_id: str,
            intuis_home,
    ) -> None:
        """Initialize the schedule data sensor."""
        super().__init__(coordinator)
        self._home_id = home_id
        self._intuis_home = intuis_home
        self._attr_unique_id = f"intuis_{home_id}_schedule_data"
        self._attr_name = "Intuis Schedule Data"
        self._attr_icon = "mdi:calendar-clock"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def device_info(self):
        """Return device info for this entity."""
        return {
            "identifiers": {(DOMAIN, self._home_id)},
            "name": "Intuis Home",
            "manufacturer": "Muller / Netatmo",
            "model": "Intuis",
        }

    @property
    def native_value(self) -> str | None:
        """Return the name of the active schedule."""
        home = self.coordinator.data.get("intuis_home") if isinstance(self.coordinator.data, dict) else self.coordinator.data
        if not home or not hasattr(home, 'schedules') or not home.schedules:
            return None
        for schedule in home.schedules:
            if isinstance(schedule, IntuisThermSchedule) and schedule.selected:
                return schedule.name
        return None

    @property
    def extra_state_attributes(self) -> dict:
        """Return schedule summary data as attributes.
        
        Note: To avoid exceeding the 16KB attribute limit, we only include
        essential data here. Full schedule details are available via individual
        schedule sensors or the sync_schedule service.
        """
        home = self.coordinator.data.get("intuis_home") if isinstance(self.coordinator.data, dict) else self.coordinator.data
        if not home or not hasattr(home, 'schedules') or not home.schedules:
            return {"schedules": []}
        
        schedules_summary = []
        
        for schedule in home.schedules:
            if not isinstance(schedule, IntuisThermSchedule):
                continue
            
            # Only include essential schedule info (no detailed rooms_temp)
            zones_summary = []
            if schedule.zones:
                for zone in schedule.zones:
                    if isinstance(zone, IntuisThermZone):
                        zones_summary.append({
                            "id": zone.id,
                            "name": zone.name,
                        })
            
            schedules_summary.append({
                "schedule_id": schedule.id,
                "name": schedule.name,
                "selected": schedule.selected,
                "timetable_count": len(schedule.timetables) if schedule.timetables else 0,
                "zones": zones_summary,
                "away_temp": schedule.away_temp,
                "hg_temp": schedule.hg_temp,
            })
        
        return {
            "schedules": schedules_summary,
            "active_schedule": self.native_value
        }


class IntuisIndividualScheduleSensor(CoordinatorEntity, SensorEntity):
    """Sensor exposing individual schedule data for UI integration.
    
    Each schedule gets its own sensor with weekly_timetable, zones, and 
    room_temperatures as attributes. The entity_id is based on schedule_id
    to be robust against renames.
    """

    def __init__(
            self,
            coordinator,
            home_id: str,
            intuis_home,
            schedule: IntuisThermSchedule,
    ) -> None:
        """Initialize the individual schedule sensor."""
        super().__init__(coordinator)
        self._home_id = home_id
        self._intuis_home = intuis_home
        self._schedule_id = schedule.id
        # Use schedule_id for unique_id to be robust against renames
        self._attr_unique_id = f"intuis_{home_id}_schedule_{schedule.id}"
        self._attr_icon = "mdi:calendar-week"

    def _get_schedule(self) -> IntuisThermSchedule | None:
        """Get the current schedule from coordinator data."""
        home = self.coordinator.data.get("intuis_home") if isinstance(self.coordinator.data, dict) else self.coordinator.data
        if not home or not hasattr(home, 'schedules') or not home.schedules:
            return None
        for schedule in home.schedules:
            if isinstance(schedule, IntuisThermSchedule) and schedule.id == self._schedule_id:
                return schedule
        return None

    def _get_all_schedules(self) -> list:
        """Get all schedules for available_schedules attribute."""
        home = self.coordinator.data.get("intuis_home") if isinstance(self.coordinator.data, dict) else self.coordinator.data
        if not home or not hasattr(home, 'schedules') or not home.schedules:
            return []
        result = []
        for schedule in home.schedules:
            if isinstance(schedule, IntuisThermSchedule):
                result.append({
                    "id": schedule.id,
                    "name": schedule.name,
                    "selected": schedule.selected
                })
        return result

    @property
    def name(self) -> str:
        """Return the name of the schedule, updated dynamically."""
        schedule = self._get_schedule()
        if schedule:
            return f"Schedule {schedule.name}"
        return f"Schedule {self._schedule_id[-6:]}"

    @property
    def device_info(self):
        """Return device info for this entity."""
        return {
            "identifiers": {(DOMAIN, self._home_id)},
            "name": "Intuis Home",
            "manufacturer": "Muller / Netatmo",
            "model": "Intuis",
        }

    @property
    def native_value(self) -> str | None:
        """Return the schedule name as state."""
        schedule = self._get_schedule()
        return schedule.name if schedule else None

    @property
    def extra_state_attributes(self) -> dict:
        """Return schedule data as attributes compatible with Node-RED format."""
        schedule = self._get_schedule()
        if not schedule:
            return {}
        
        home = self.coordinator.data.get("intuis_home") if isinstance(self.coordinator.data, dict) else self.coordinator.data
        
        # Build rooms map for room names
        rooms_map = {}
        if home and hasattr(home, 'rooms') and home.rooms:
            for room_id, room in home.rooms.items():
                rooms_map[str(room_id)] = room.name if hasattr(room, 'name') else str(room_id)
        
        # Convert timetable to weekly format (Monday, Tuesday, etc.)
        weekly_timetable = self._convert_to_weekly_timetable(schedule)
        
        # Build zones with room_temperatures as dict (room_id -> temp)
        zones = []
        for zone in schedule.zones:
            if isinstance(zone, IntuisThermZone):
                room_temperatures = {}
                for rt in zone.rooms_temp:
                    room_temperatures[str(rt.room_id)] = rt.temp
                zones.append({
                    "id": zone.id,
                    "name": zone.name,
                    "type": zone.type,
                    "room_temperatures": room_temperatures
                })
        
        return {
            "schedule_id": schedule.id,
            "schedule_name": schedule.name,
            "is_active": schedule.selected,
            "is_default": schedule.default,
            "away_temperature": schedule.away_temp,
            "frost_guard_temperature": schedule.hg_temp,
            "weekly_timetable": weekly_timetable,
            "zones": zones,
            "zones_count": len(zones),
            "available_schedules": self._get_all_schedules(),
        }

    def _convert_to_weekly_timetable(self, schedule: IntuisThermSchedule) -> dict:
        """Convert m_offset timetable to weekly format with day names."""
        DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        
        # Build zone_id to name map
        zone_names = {}
        for zone in schedule.zones:
            if isinstance(zone, IntuisThermZone):
                zone_names[zone.id] = zone.name
        
        # Group timetable entries by day
        weekly = {day: [] for day in DAY_NAMES}
        
        for tt in sorted(schedule.timetables, key=lambda t: t.m_offset):
            day_index = tt.m_offset // MINUTES_PER_DAY
            if 0 <= day_index < 7:
                minutes_in_day = tt.m_offset % MINUTES_PER_DAY
                hours = minutes_in_day // 60
                mins = minutes_in_day % 60
                time_str = f"{hours:02d}:{mins:02d}"
                zone_name = zone_names.get(tt.zone_id, f"Zone {tt.zone_id}")
                
                weekly[DAY_NAMES[day_index]].append({
                    "time": time_str,
                    "zone": zone_name
                })
        
        # Remove empty days
        return {day: slots for day, slots in weekly.items() if slots}

