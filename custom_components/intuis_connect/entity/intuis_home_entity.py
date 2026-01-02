"""Home-level device and entities for Intuis Connect."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass, SensorDeviceClass
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
import homeassistant.util.dt as dt_util

from .intuis_home import IntuisHome
from .intuis_schedule import IntuisThermSchedule, IntuisThermZone, IntuisTimetable
from ..entity.intuis_entity import IntuisDataUpdateCoordinator
from ..utils.const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Minutes in a week
MINUTES_IN_WEEK = 7 * 24 * 60  # 10080


class IntuisHomeEntity(CoordinatorEntity[IntuisDataUpdateCoordinator], SensorEntity):
    """Base class for Intuis home-level entities."""

    def __init__(
            self,
            coordinator: IntuisDataUpdateCoordinator,
            home_id: str,
            entity_type: str,
            home_property: str,
            icon: str,
            available: bool = False,
            measurement: bool = False,
    ) -> None:
        """Initialize the home entity."""
        super().__init__(coordinator)
        self._home_id = home_id
        self._attr_name = f"Intuis Home {home_property}"
        self._attr_unique_id = f"intuis_{home_id}_home_{entity_type}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{home_id}_home")},
            name="Intuis Home",
            manufacturer="Muller Intuitiv (Netatmo)",
            model="Home Controller",
            suggested_area="Home",
        )
        self._attr_icon = icon
        self._property = home_property
        self._attr_available = available
        self._attr_entity_registry_enabled_default = False
        if measurement:
            self._attr_state_class = SensorStateClass.MEASUREMENT

    def _get_home(self) -> IntuisHome:
        """Get the home data from coordinator."""
        return self.coordinator.data.get("intuis_home")

    @property
    def native_value(self) -> Any:
        """Return the value of the home property."""
        home_data = self._get_home()
        if not home_data:
            _LOGGER.warning("Home data not available for home ID %s", self._home_id)
            return None

        try:
            # Use operator.attrgetter for potentially nested attributes
            from operator import attrgetter
            getter = attrgetter(self._property)
            return getter(home_data)
        except AttributeError as e:
            _LOGGER.error(
                "Failed to get property '%s' from home_data: %s",
                self._property,
                str(e)
            )
            return None

class IntuisHomeConfigEntity(IntuisHomeEntity):
    """Base class for Intuis home-level configuration entities."""

    def __init__(
            self,
            coordinator: IntuisDataUpdateCoordinator,
            home_id: str,
            entity_type: str,
            home_property: str,
            icon: str,
            available: bool = False,
            measurement: bool = False,
    ) -> None:
        """Initialize the home configuration entity."""
        super().__init__(coordinator, home_id, entity_type, home_property, icon, available, measurement)

    def _get_home(self) -> IntuisHome:
        """Get the home data from coordinator."""
        return self.coordinator.data.get("home_config")


class IntuisHomeSensorDefinition:
    """Definition of a sensor entity for Intuis home-level data."""

    def __init__(self, entity_type: str, home_property: str, icon: str, available: bool = False, measurement: bool = False, ) -> None:
        """Initialize the sensor definition."""
        self.entity_type = entity_type
        self.home_property = home_property
        self.icon = icon
        self.measurement = measurement
        self.available = available


intuis_home_entities: list[IntuisHomeSensorDefinition] = [
    IntuisHomeSensorDefinition("Name", "name", "mdi:home", True),
    IntuisHomeSensorDefinition("Country", "country", "mdi:flag"),
    IntuisHomeSensorDefinition("Timezone", "timezone", "mdi:map-clock"),
    IntuisHomeSensorDefinition("Altitude", "altitude", "mdi:elevation-rise", False, True),
    IntuisHomeSensorDefinition("City", "city", "mdi:city"),
    IntuisHomeSensorDefinition("Currency Code", "currency_code", "mdi:currency-usd"),
    IntuisHomeSensorDefinition("Number of Users", "nb_users", "mdi:account-multiple"),
    IntuisHomeSensorDefinition("Temperature Control Mode", "temperature_control_mode", "mdi:thermometer",  True),
    IntuisHomeSensorDefinition("Thermostat Mode", "therm_mode", "mdi:thermostat", True),
    IntuisHomeSensorDefinition("Thermostat Setpoint Default Duration",
                               "therm_setpoint_default_duration", "mdi:timer-sand",  True),
    IntuisHomeSensorDefinition("Thermostat Heating Priority",
                               "therm_heating_priority", "mdi:priority-high",  True),
    IntuisHomeSensorDefinition("Contract Power Unit", "contract_power_unit", "mdi:flash", True),
]

intuis_home_config_entities: list[IntuisHomeSensorDefinition] = [
    IntuisHomeSensorDefinition("Absence Detection", "absence_detection", "mdi:account-off",  True),
    IntuisHomeSensorDefinition("Anticipation", "anticipation", "mdi:clock-fast",  True),
    IntuisHomeSensorDefinition("Balancing", "balancing", "mdi:balance-scale",  True),
    IntuisHomeSensorDefinition("Debug Enabled", "debug_enabled", "mdi:bug-check",  True),
    IntuisHomeSensorDefinition("Offload", "offload", "mdi:power-plug-off", True),
    IntuisHomeSensorDefinition("Open Window Detection", "open_window", "mdi:window-open-variant", True),
    IntuisHomeSensorDefinition("Presence Threshold", "presence_threshold", "mdi:eye-check-outline"),
    IntuisHomeSensorDefinition("Schedule Optimization", "schedule_optimization", "mdi:calendar-check-outline"),
    IntuisHomeSensorDefinition("Temperature Lowering Mode",
                               "temp_lowering_mode", "mdi:temperature-celsius"),
    IntuisHomeSensorDefinition("Thermostat Setpoint Day Color Red EJP Offset",
                               "therm_setpoint_day_color_red_ejp_offset", "mdi:thermometer-alert"),
    IntuisHomeSensorDefinition("Thermostat Setpoint Day Color Red EJP Type",
                               "therm_setpoint_day_color_red_ejp_type", "mdi:thermometer-alert"),
    IntuisHomeSensorDefinition("Thermostat Setpoint Day Color White Offset",
                               "therm_setpoint_day_color_white_offset", "mdi:thermometer-alert"),
    IntuisHomeSensorDefinition("Thermostat Setpoint Day Color White Type",
                               "therm_setpoint_day_color_white_type", "mdi:thermometer-alert"),
]


def _get_current_minute_offset() -> int:
    """Calculate current minute offset in the week (0 = Monday 00:00)."""
    now = datetime.now()
    # Python weekday: Monday = 0, Sunday = 6
    day_of_week = now.weekday()
    minutes_today = now.hour * 60 + now.minute
    return day_of_week * 1440 + minutes_today


def _get_active_schedule(intuis_home: IntuisHome) -> IntuisThermSchedule | None:
    """Get the currently active thermostat schedule."""
    if not intuis_home or not intuis_home.schedules:
        return None
    for schedule in intuis_home.schedules:
        if isinstance(schedule, IntuisThermSchedule) and schedule.selected:
            return schedule
    return None


def _get_current_zone_from_schedule(schedule: IntuisThermSchedule, current_offset: int) -> IntuisThermZone | None:
    """Get the active zone for a given minute offset."""
    if not schedule or not schedule.timetables:
        return None

    # Sort timetables by m_offset to find the active one
    sorted_timetables = sorted(schedule.timetables, key=lambda t: t.m_offset)

    active_zone_id = None
    for timetable in sorted_timetables:
        if timetable.m_offset <= current_offset:
            active_zone_id = timetable.zone_id
        else:
            break

    # If no zone found (current_offset before first timetable), wrap to last zone of week
    if active_zone_id is None and sorted_timetables:
        active_zone_id = sorted_timetables[-1].zone_id

    if active_zone_id is None:
        return None

    # Find the zone object
    for zone in schedule.zones:
        if isinstance(zone, IntuisThermZone) and zone.id == active_zone_id:
            return zone

    return None


def _get_next_zone_change(schedule: IntuisThermSchedule, current_offset: int) -> tuple[IntuisTimetable | None, int]:
    """Get the next zone change timetable and minutes until it occurs."""
    if not schedule or not schedule.timetables:
        return None, 0

    sorted_timetables = sorted(schedule.timetables, key=lambda t: t.m_offset)

    # Find next timetable entry after current_offset
    for timetable in sorted_timetables:
        if timetable.m_offset > current_offset:
            minutes_until = timetable.m_offset - current_offset
            return timetable, minutes_until

    # Wrap to first timetable of next week
    if sorted_timetables:
        first_timetable = sorted_timetables[0]
        minutes_until = (MINUTES_IN_WEEK - current_offset) + first_timetable.m_offset
        return first_timetable, minutes_until

    return None, 0


class IntuisCurrentZoneSensor(CoordinatorEntity[IntuisDataUpdateCoordinator], SensorEntity):
    """Sensor showing the currently active zone name."""

    _attr_icon = "mdi:home-thermometer"
    _attr_has_entity_name = True

    def __init__(
            self,
            coordinator: IntuisDataUpdateCoordinator,
            home_id: str,
    ) -> None:
        """Initialize the current zone sensor."""
        super().__init__(coordinator)
        self._home_id = home_id
        self._attr_name = "Current Zone"
        self._attr_unique_id = f"intuis_{home_id}_current_zone"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{home_id}_home")},
            name="Intuis Home",
            manufacturer="Muller Intuitiv (Netatmo)",
            model="Home Controller",
        )

    def _get_home(self) -> IntuisHome | None:
        """Get the home data from coordinator."""
        return self.coordinator.data.get("intuis_home")

    @property
    def native_value(self) -> str | None:
        """Return the current zone name."""
        home = self._get_home()
        schedule = _get_active_schedule(home)
        if not schedule:
            return None

        current_offset = _get_current_minute_offset()
        zone = _get_current_zone_from_schedule(schedule, current_offset)
        return zone.name if zone else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        attrs = {}
        home = self._get_home()
        schedule = _get_active_schedule(home)
        if not schedule:
            return attrs

        current_offset = _get_current_minute_offset()
        zone = _get_current_zone_from_schedule(schedule, current_offset)

        if zone:
            attrs["zone_id"] = zone.id
            attrs["zone_type"] = zone.type
            attrs["schedule_name"] = schedule.name
            # Include room temperatures for this zone
            room_temps = {}
            for rt in zone.rooms_temp:
                room_temps[rt.room_id] = rt.temp
            attrs["room_temperatures"] = room_temps

        return attrs


class IntuisNextZoneChangeSensor(CoordinatorEntity[IntuisDataUpdateCoordinator], SensorEntity):
    """Sensor showing when the next zone change occurs."""

    _attr_icon = "mdi:calendar-clock"
    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(
            self,
            coordinator: IntuisDataUpdateCoordinator,
            home_id: str,
    ) -> None:
        """Initialize the next zone change sensor."""
        super().__init__(coordinator)
        self._home_id = home_id
        self._attr_name = "Next Zone Change"
        self._attr_unique_id = f"intuis_{home_id}_next_zone_change"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{home_id}_home")},
            name="Intuis Home",
            manufacturer="Muller Intuitiv (Netatmo)",
            model="Home Controller",
        )

    def _get_home(self) -> IntuisHome | None:
        """Get the home data from coordinator."""
        return self.coordinator.data.get("intuis_home")

    @property
    def native_value(self) -> datetime | None:
        """Return the timestamp of the next zone change."""
        home = self._get_home()
        schedule = _get_active_schedule(home)
        if not schedule:
            return None

        current_offset = _get_current_minute_offset()
        next_timetable, minutes_until = _get_next_zone_change(schedule, current_offset)

        if next_timetable and minutes_until > 0:
            return dt_util.now() + timedelta(minutes=minutes_until)
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        attrs = {}
        home = self._get_home()
        schedule = _get_active_schedule(home)
        if not schedule:
            return attrs

        current_offset = _get_current_minute_offset()
        next_timetable, minutes_until = _get_next_zone_change(schedule, current_offset)

        if next_timetable:
            # Find the zone for the next timetable
            for zone in schedule.zones:
                if isinstance(zone, IntuisThermZone) and zone.id == next_timetable.zone_id:
                    attrs["next_zone_name"] = zone.name
                    attrs["next_zone_id"] = zone.id
                    break
            attrs["minutes_until_change"] = minutes_until

        return attrs


class IntuisScheduleSummarySensor(CoordinatorEntity[IntuisDataUpdateCoordinator], SensorEntity):
    """Sensor providing a summary of a specific schedule.

    One sensor is created per schedule, allowing users to select which
    schedule to display in the intuis-schedule-card.
    """

    _attr_icon = "mdi:calendar-week"
    _attr_has_entity_name = True

    def __init__(
            self,
            coordinator: IntuisDataUpdateCoordinator,
            home_id: str,
            schedule: IntuisThermSchedule,
    ) -> None:
        """Initialize the schedule summary sensor for a specific schedule."""
        super().__init__(coordinator)
        self._home_id = home_id
        self._schedule_id = schedule.id
        self._schedule_name = schedule.name or f"Schedule {schedule.id}"
        self._attr_name = f"Schedule {self._schedule_name}"
        self._attr_unique_id = f"intuis_{home_id}_schedule_{schedule.id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{home_id}_home")},
            name="Intuis Home",
            manufacturer="Muller Intuitiv (Netatmo)",
            model="Home Controller",
        )

    def _get_home(self) -> IntuisHome | None:
        """Get the home data from coordinator."""
        return self.coordinator.data.get("intuis_home")

    def _get_schedule(self) -> IntuisThermSchedule | None:
        """Get the specific schedule this sensor represents."""
        home = self._get_home()
        if not home or not home.schedules:
            return None
        for schedule in home.schedules:
            if isinstance(schedule, IntuisThermSchedule) and schedule.id == self._schedule_id:
                return schedule
        return None

    @property
    def native_value(self) -> str | None:
        """Return the schedule name."""
        schedule = self._get_schedule()
        return schedule.name if schedule else self._schedule_name

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the full schedule details as attributes."""
        attrs = {}
        home = self._get_home()
        schedule = self._get_schedule()
        if not schedule:
            return attrs

        attrs["schedule_id"] = schedule.id
        attrs["is_default"] = schedule.default
        attrs["is_active"] = schedule.selected
        attrs["away_temperature"] = schedule.away_temp
        attrs["frost_guard_temperature"] = schedule.hg_temp

        # Build zones list
        zones_info = []
        for zone in schedule.zones:
            if isinstance(zone, IntuisThermZone):
                zone_info = {
                    "id": zone.id,
                    "name": zone.name,
                    "type": zone.type,
                    "room_temperatures": {rt.room_id: rt.temp for rt in zone.rooms_temp}
                }
                zones_info.append(zone_info)
        attrs["zones"] = zones_info
        attrs["zones_count"] = len(zones_info)

        # Build weekly timetable summary (day -> list of changes)
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        weekly_summary = {}
        for day_idx, day_name in enumerate(days):
            day_start = day_idx * 1440
            day_end = day_start + 1440
            day_entries = []
            for tt in sorted(schedule.timetables, key=lambda t: t.m_offset):
                if day_start <= tt.m_offset < day_end:
                    time_in_day = tt.m_offset - day_start
                    hour = time_in_day // 60
                    minute = time_in_day % 60
                    zone_name = None
                    for zone in schedule.zones:
                        if isinstance(zone, IntuisThermZone) and zone.id == tt.zone_id:
                            zone_name = zone.name
                            break
                    day_entries.append({
                        "time": f"{hour:02d}:{minute:02d}",
                        "zone": zone_name or f"Zone {tt.zone_id}"
                    })
            if day_entries:
                weekly_summary[day_name] = day_entries
        attrs["weekly_timetable"] = weekly_summary

        # All available schedules (for switching)
        available_schedules = []
        if home and home.schedules:
            for s in home.schedules:
                if isinstance(s, IntuisThermSchedule):
                    available_schedules.append({
                        "id": s.id,
                        "name": s.name,
                        "selected": s.selected
                    })
        attrs["available_schedules"] = available_schedules

        return attrs


def provide_home_sensors(
        coordinator: IntuisDataUpdateCoordinator,
        home_id: str,
        intuis_home: IntuisHome | None = None,
) -> list[SensorEntity]:
    """Set up home-level sensor entities."""

    result: list[SensorEntity] = []
    for entity_def in intuis_home_entities:
        result.append(
            IntuisHomeEntity(
                coordinator,
                home_id,
                entity_def.entity_type,
                entity_def.home_property,
                entity_def.icon,
                entity_def.available,
                entity_def.measurement
            )
        )
    for entity_def in intuis_home_config_entities:
        result.append(
            IntuisHomeConfigEntity(
                coordinator,
                home_id,
                entity_def.entity_type,
                entity_def.home_property,
                entity_def.icon,
                entity_def.available,
                entity_def.measurement
            )
        )

    # Add schedule-related sensors
    result.append(IntuisCurrentZoneSensor(coordinator, home_id))
    result.append(IntuisNextZoneChangeSensor(coordinator, home_id))

    # Create one schedule summary sensor per home-level thermostat schedule
    # Filter out room-specific schedules by checking for zones and timetables
    if intuis_home and intuis_home.schedules:
        for schedule in intuis_home.schedules:
            if isinstance(schedule, IntuisThermSchedule):
                # Only include schedules that have zones defined (home-level schedules)
                # Room-specific or backup schedules typically have no zones
                has_zones = schedule.zones and len(schedule.zones) > 0
                has_timetables = schedule.timetables and len(schedule.timetables) > 0

                if has_zones and has_timetables:
                    _LOGGER.debug(
                        "Creating schedule summary sensor for: %s (ID: %s, zones: %d, timetables: %d)",
                        schedule.name, schedule.id, len(schedule.zones), len(schedule.timetables)
                    )
                    result.append(IntuisScheduleSummarySensor(coordinator, home_id, schedule))
                else:
                    _LOGGER.debug(
                        "Skipping schedule %s (ID: %s) - no zones or timetables (zones: %s, timetables: %s)",
                        schedule.name, schedule.id,
                        len(schedule.zones) if schedule.zones else 0,
                        len(schedule.timetables) if schedule.timetables else 0
                    )

    return result
