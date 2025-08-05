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

from custom_components.intuis_connect import IntuisAPI
from custom_components.intuis_connect.entity.intuis_entity import IntuisDataUpdateCoordinator, IntuisEntity
from custom_components.intuis_connect.entity.intuis_room import IntuisRoom
from custom_components.intuis_connect.helper import get_basic_utils

_LOGGER = logging.getLogger(__name__)


class IntuisScheduleCalendar(
    CoordinatorEntity[IntuisDataUpdateCoordinator], CalendarEntity, IntuisEntity
):
    """Expose each room’s weekly schedule as a Calendar."""

    def __init__(
            self,
            coordinator: IntuisDataUpdateCoordinator,
            api: IntuisAPI,
            home_id: str,
            room: IntuisRoom
    ) -> None:
        """Initialize the calendar entity."""
        CoordinatorEntity.__init__(self, coordinator)
        CalendarEntity.__init__(self)
        IntuisEntity.__init__(self, coordinator, room, home_id, f"{room.name} Schedule", "schedule_calendar")

        self._api = api

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming event slot, or None."""
        now = dt_util.utcnow()
        for ev in self.event_list:
            if ev.start_datetime_local and ev.start_datetime_local > now:
                return ev
        return None

    @property
    def event_list(self) -> list[CalendarEvent]:
        """Return all schedule slots for the calendar."""
        events: list[CalendarEvent] = []
        slots = self.coordinator.data.get("schedule", {}).get(self._room.id, [])
        for slot in slots:
            start = dt_util.parse_datetime(slot["start"])
            end = dt_util.parse_datetime(slot.get("end")) or (
                    start + timedelta(hours=1)
            )
            if not start:
                continue
            ev: CalendarEvent = CalendarEvent(
                start=start,
                end=end,
                summary=f"{slot['temp']}°C",
                description=f"{self._attr_name}: {slot['temp']}°C",
                uid=slot.get("id"),
            )
            events.append(ev)
        return events

    async def async_get_events(
            self,
            hass: HomeAssistant,
            start_date: datetime,
            end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return calendar events within a datetime range."""
        return [
            ev
            for ev in self.event_list
            if ev.start_datetime_local
               and start_date <= ev.start_datetime_local <= end_date
        ]

    async def async_create_event(self, **kwargs: Any) -> None:
        """Add a new event to the calendar."""
        temp = float(kwargs["summary"].rstrip("°C"))
        start_val: datetime = kwargs["start"]
        end_val: datetime = kwargs.get("end") or (start_val + timedelta(hours=1))
        start = start_val.isoformat()
        end = end_val.isoformat()
        try:
            await self._api.async_set_schedule_slot(
                self._home_id,
                self.coordinator.data.get("active_schedule_id"),
                self._get_room().id,
                start,
                end,
                temp,
            )
        except Exception as err:
            _LOGGER.error("Failed to create schedule slot: %s", err)
            raise
        await self.coordinator.async_request_refresh()

    async def async_delete_event(
            self,
            uid: str,
            recurrence_id: str | None = None,
            recurrence_range: str | None = None,
    ) -> None:
        """Delete an event on the calendar."""
        try:
            await self._api.async_delete_schedule_slot(self._home_id, uid)
        except Exception as err:
            _LOGGER.error("Failed to delete schedule slot: %s", err)
            raise
        await self.coordinator.async_request_refresh()


async def async_setup_entry(
        hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the climate entities."""
    coordinator, home_id, rooms, api = get_basic_utils(hass, entry)

    entities = []
    for room_id in rooms:
        entities.append(
            IntuisScheduleCalendar(coordinator, api, home_id, rooms.get(room_id))
        )
    async_add_entities(entities, update_before_add=True)
