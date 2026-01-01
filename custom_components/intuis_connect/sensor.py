"""Sensor platform for Intuis Connect."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfTemperature, UnitOfEnergy
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .entity.intuis_entity import IntuisEntity
from .entity.intuis_home_entity import provide_home_sensors
from .entity.intuis_room import IntuisRoom
from .entity.intuis_schedule import IntuisThermSchedule, IntuisThermZone
from .utils.const import DOMAIN
from .utils.helper import get_basic_utils

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Intuis Connect sensors from a config entry."""
    coordinator, home_id, rooms, api = get_basic_utils(hass, entry)
    intuis_home = hass.data[DOMAIN][entry.entry_id].get("intuis_home")

    entities: list[IntuisSensor] = []
    for room_id in rooms:
        room = rooms.get(room_id)
        entities.append(IntuisTemperatureSensor(coordinator, home_id, room))
        entities.append(IntuisTargetTemperatureSensor(coordinator, home_id, room))
        entities.append(IntuisMullerTypeSensor(coordinator, home_id, room))
        entities.append(IntuisEnergySensor(coordinator, home_id, room))
        entities.append(IntuisMinutesSensor(coordinator, home_id, room))
        entities.append(IntuisSetpointEndTimeSensor(coordinator, home_id, room))
        entities.append(IntuisScheduledTempSensor(coordinator, home_id, room, intuis_home))

    entities += provide_home_sensors(coordinator, home_id)
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

    @property
    def native_value(self) -> str:
        """Return the current device type."""
        # Ensure we handle None values gracefully
        muller_type = self._room.muller_type
        if muller_type is None:
            return ""
        return muller_type


class IntuisTargetTemperatureSensor(IntuisSensor):
    """Specialized sensor for target temperature."""

    def __init__(self, coordinator, home_id: str, room: IntuisRoom) -> None:
        """Initialize the target temperature sensor."""
        super().__init__(
            coordinator,
            home_id,
            room,
            "target_temperature",
            "Setpoint",
            UnitOfTemperature.CELSIUS,
            None,
        )
        self._attr_icon = "mdi:thermometer"

    @property
    def native_value(self) -> float:
        """Return the current target temperature."""
        # Ensure we handle None values gracefully
        target_temp = self._room.target_temperature
        if target_temp is None:
            return 0.0
        return target_temp


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

    @property
    def native_value(self) -> float:
        """Return the current temperature value."""
        # Ensure we handle None values gracefully
        temperature = self._room.temperature
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

    @property
    def native_value(self) -> int:
        """Return the current heating minutes value."""
        # Ensure we handle None values gracefully
        minutes = self._room.minutes
        if minutes is None:
            return 0
        return minutes


class IntuisEnergySensor(IntuisSensor):
    """Specialized sensor for daily energy consumption.

    This sensor tracks cumulative daily energy consumption (max seen today, never decreases).
    The value resets at midnight to start tracking the new day's consumption.
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
        self._attr_state_class = SensorStateClass.TOTAL

        # Track daily maximum energy (never decrease within a day)
        self._daily_max_energy: float = 0.0
        self._last_reset_date: datetime | None = None

    @property
    def native_value(self) -> float:
        """Return the cumulative daily energy value (max seen today)."""
        if self._room is None:
            return self._daily_max_energy

        current_energy = self._room.energy or 0.0
        now = datetime.now()

        # Reset daily max on new day
        if self._last_reset_date is None or self._last_reset_date.date() != now.date():
            self._daily_max_energy = current_energy
            self._last_reset_date = now
            _LOGGER.debug(
                "New day for %s, reset daily max to %.3f kWh",
                self._room.name, current_energy
            )
        elif current_energy > self._daily_max_energy:
            # Update max if current is higher
            self._daily_max_energy = current_energy
            _LOGGER.debug(
                "Updated daily max for %s to %.3f kWh",
                self._room.name, current_energy
            )

        return self._daily_max_energy


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

    @property
    def native_value(self) -> datetime | None:
        """Return the end time of the current override as a datetime."""
        if self._room is None:
            return None
        end_ts = self._room.therm_setpoint_end_time
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
        # m_offset: 0 = Monday 00:00, 1440 = Tuesday 00:00, etc.
        now = datetime.now()
        # Python weekday: Monday = 0, Sunday = 6
        day_of_week = now.weekday()
        minutes_today = now.hour * 60 + now.minute
        current_offset = day_of_week * 1440 + minutes_today

        # Find the active zone for this time
        active_zone_id = None
        for timetable in active_schedule.timetables:
            if timetable.m_offset <= current_offset:
                active_zone_id = timetable.zone_id

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
        room_id = self._room.id if self._room else None
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
            room_id = self._room.id if self._room else None
            if room_id:
                for room_config in zone.rooms:
                    if room_config.id == room_id and room_config.therm_setpoint_fp:
                        attrs["preset_mode"] = room_config.therm_setpoint_fp

        return attrs
