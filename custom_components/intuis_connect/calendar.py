"""Calendar support for Intuis Connect room schedules."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import homeassistant.util.dt as dt_util
from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo

from .intuis_api.api import IntuisAPI
from .entity.intuis_entity import IntuisDataUpdateCoordinator
from .entity.intuis_home import IntuisHome
from .entity.intuis_schedule import IntuisThermSchedule, IntuisThermZone
from .utils.const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Minutes in a day/week
MINUTES_IN_DAY = 24 * 60  # 1440
MINUTES_IN_WEEK = 7 * MINUTES_IN_DAY  # 10080


def _get_active_schedule(intuis_home: IntuisHome) -> IntuisThermSchedule | None:
    """Get the currently active thermostat schedule."""
    if not intuis_home or not intuis_home.schedules:
        return None
    for schedule in intuis_home.schedules:
        if isinstance(schedule, IntuisThermSchedule) and schedule.selected:
            return schedule
    return None


def _minute_offset_to_datetime(m_offset: int, week_start: datetime) -> datetime:
    """Convert a minute offset to a datetime within the given week."""
    return week_start + timedelta(minutes=m_offset)


def _get_zone_by_id(schedule: IntuisThermSchedule, zone_id: int) -> IntuisThermZone | None:
    """Get a zone by its ID."""
    for zone in schedule.zones:
        if isinstance(zone, IntuisThermZone) and zone.id == zone_id:
            return zone
    return None


class IntuisScheduleCalendar(
    CoordinatorEntity[IntuisDataUpdateCoordinator], CalendarEntity
):
    """Expose the home's weekly schedule as a Calendar."""

    _attr_has_entity_name = True

    def __init__(
            self,
            coordinator: IntuisDataUpdateCoordinator,
            api: IntuisAPI,
            home_id: str,
            intuis_home: IntuisHome,
    ) -> None:
        """Initialize the calendar entity."""
        CoordinatorEntity.__init__(self, coordinator)
        CalendarEntity.__init__(self)

        self._api = api
        self._home_id = home_id
        self._intuis_home = intuis_home

        self._attr_name = "Heating Schedule"
        self._attr_unique_id = f"intuis_{home_id}_schedule_calendar"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{home_id}_home")},
            name="Intuis Home",
            manufacturer="Muller Intuitiv (Netatmo)",
            model="Home Controller",
        )

    def _get_home(self) -> IntuisHome:
        """Get the home data from coordinator."""
        return self.coordinator.data.get("intuis_home") or self._intuis_home

    def _get_week_start(self, reference: datetime) -> datetime:
        """Get the Monday 00:00 of the week containing the reference date."""
        # Get the Monday of the current week
        days_since_monday = reference.weekday()
        monday = reference.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_since_monday)
        return monday

    def _build_events_for_week(self, week_start: datetime) -> list[CalendarEvent]:
        """Build calendar events for a specific week based on the schedule timetables."""
        events: list[CalendarEvent] = []

        home = self._get_home()
        schedule = _get_active_schedule(home)
        if not schedule or not schedule.timetables:
            return events

        # Sort timetables by m_offset
        sorted_timetables = sorted(schedule.timetables, key=lambda t: t.m_offset)

        for i, timetable in enumerate(sorted_timetables):
            zone = _get_zone_by_id(schedule, timetable.zone_id)
            if not zone:
                continue

            # Calculate start time
            start_dt = _minute_offset_to_datetime(timetable.m_offset, week_start)

            # Calculate end time (next timetable start or end of week)
            if i + 1 < len(sorted_timetables):
                end_offset = sorted_timetables[i + 1].m_offset
            else:
                # Wrap to first timetable of next week
                end_offset = MINUTES_IN_WEEK

            end_dt = _minute_offset_to_datetime(end_offset, week_start)

            # Build summary with zone temperatures
            room_temps = []
            for rt in zone.rooms_temp:
                room_temps.append(f"{rt.temp}°C")
            temp_str = ", ".join(room_temps) if room_temps else "N/A"

            event = CalendarEvent(
                start=start_dt,
                end=end_dt,
                summary=f"{zone.name}",
                description=f"Zone: {zone.name}\nTemperatures: {temp_str}",
                uid=f"{schedule.id}_{timetable.m_offset}_{timetable.zone_id}",
            )
            events.append(event)

        return events

    @property
    def event(self) -> CalendarEvent | None:
        """Return the current/next upcoming event."""
        now = dt_util.now()
        week_start = self._get_week_start(now)
        events = self._build_events_for_week(week_start)

        # Find the current or next event
        for ev in events:
            if ev.end and ev.end > now:
                return ev

        # If no event found in current week, check next week
        next_week_start = week_start + timedelta(days=7)
        events = self._build_events_for_week(next_week_start)
        for ev in events:
            if ev.start and ev.start > now:
                return ev

        return None

    async def async_get_events(
            self,
            hass: HomeAssistant,
            start_date: datetime,
            end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return calendar events within a datetime range."""
        all_events: list[CalendarEvent] = []

        # Generate events for each week in the range
        current_date = start_date
        while current_date <= end_date:
            week_start = self._get_week_start(current_date)
            week_events = self._build_events_for_week(week_start)

            for ev in week_events:
                # Filter events within the requested range
                if ev.start and ev.end:
                    if ev.end > start_date and ev.start < end_date:
                        # Avoid duplicates by checking UID
                        if not any(e.uid == ev.uid for e in all_events):
                            all_events.append(ev)

            # Move to next week
            current_date = week_start + timedelta(days=7)

        return sorted(all_events, key=lambda e: e.start or datetime.min)


async def async_setup_entry(
        hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the calendar entities."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: IntuisDataUpdateCoordinator = data["coordinator"]
    api: IntuisAPI = data["api"]
    intuis_home: IntuisHome = data["intuis_home"]

    # Only create calendar if there are thermostat schedules
    has_therm_schedules = any(
        isinstance(s, IntuisThermSchedule) for s in intuis_home.schedules
    )

    entities = []
    if has_therm_schedules:
        entities.append(
            IntuisScheduleCalendar(coordinator, api, intuis_home.id, intuis_home)
        )

    async_add_entities(entities, update_before_add=True)
