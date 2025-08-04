"""Calendar support for Intuis Connect room schedules."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import cast

import homeassistant.util.dt as dt_util
from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class IntuisScheduleCalendar(CoordinatorEntity, CalendarEntity):
    """Expose each room’s weekly schedule as a Calendar."""

    def __init__(
            self,
            coordinator,
            api,
            home_id: str,
            room_id: str,
            room_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._api = api
        self._home_id = home_id
        self._room_id = room_id
        self._attr_name = f"{room_name} Schedule"
        self._attr_unique_id = f"{home_id}_{room_id}_schedule"

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming event slot, or None."""
        now = dt_util.utcnow()
        slots = self.coordinator.data.get("schedule", {}).get(self._room_id, [])
        for slot in slots:
            start = dt_util.parse_datetime(slot["start"])
            if start and start >= now:
                end = dt_util.parse_datetime(slot.get("end")) or (start + timedelta(hours=1))
                event: CalendarEvent = cast(
                    CalendarEvent,
                    {
                        "start": start,
                        "end": end,
                        "summary": f"{slot['temp']}°C",
                        "description": f"{self._attr_name}: {slot['temp']}°C",
                        "id": slot.get("id"),
                    },
                )
                return event
        return None

    @property
    def event_list(self) -> list[CalendarEvent]:
        """Return all schedule slots for the calendar."""
        events: list[CalendarEvent] = []
        slots = self.coordinator.data.get("schedule", {}).get(self._room_id, [])
        for slot in slots:
            start = dt_util.parse_datetime(slot["start"])
            end = dt_util.parse_datetime(slot.get("end")) or (start + timedelta(hours=1))
            if not start:
                continue
            ev: CalendarEvent = cast(
                CalendarEvent,
                {
                    "start": start,
                    "end": end,
                    "summary": f"{slot['temp']}°C",
                    "description": f"{self._attr_name}: {slot['temp']}°C",
                    "id": slot.get("id"),
                },
            )
            events.append(ev)
        return events

    async def async_get_events(
            self,
            hass: HomeAssistant,
            start_date: dt_util.dt.datetime,
            end_date: dt_util.dt.datetime | None = None,
    ) -> list[CalendarEvent]:
        """Return calendar events within a datetime range."""
        return [
            ev for ev in self.event_list
            if ev.start >= start_date and (end_date is None or ev.start <= end_date)
        ]

    async def async_create_event(self, **event_data) -> CalendarEvent:
        """Called when the user creates/edits an event."""
        temp = float(event_data["summary"].rstrip("°C"))
        start_val = event_data["start"]
        end_val = event_data.get("end") or (start_val + timedelta(hours=1))
        start = start_val.isoformat()
        end = end_val.isoformat()
        try:
            await self._api.async_set_schedule_slot(
                self._home_id,
                self.coordinator.data.get("active_schedule_id"),
                self._room_id,
                start,
                end,
                temp,
            )
        except Exception as err:
            _LOGGER.error("Failed to create schedule slot: %s", err)
            raise
        await self.coordinator.async_request_refresh()
        created: CalendarEvent = cast(
            CalendarEvent,
            {
                "start": start_val,
                "end": end_val,
                "summary": f"{temp}°C",
                "description": f"{self._attr_name}: {temp}°C",
                # 'id' not returned immediately; calendar will refresh
            },
        )
        return created

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


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Calendar entities for each room."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    api = data["api"]
    home_id = data["home_id"]
    rooms = data["rooms"]

    entities: list[IntuisScheduleCalendar] = []
    for room_id, room_name in rooms.items():
        entities.append(
            IntuisScheduleCalendar(coordinator, api, home_id, room_id, room_name)
        )

    async_add_entities(entities)
