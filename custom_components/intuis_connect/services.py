"""Service handlers for Intuis Connect integration.

This module contains all service registration and handling logic,
including dynamic services.yaml generation for the Home Assistant UI.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import voluptuous as vol
import yaml
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TimeSelector,
    TimeSelectorConfig,
)

from .entity.intuis_home import IntuisHome
from .entity.intuis_schedule import IntuisThermSchedule, IntuisThermZone, IntuisTimetable
from .intuis_api.api import IntuisAPI
from .timetable import (
    find_zone_at_offset,
    upsert_timetable_entry,
    remove_consecutive_duplicates,
    DAYS_OF_WEEK,
    DAYS_OF_WEEK_FR,
    MINUTES_PER_DAY,
)
from .utils.const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# Service names
SERVICE_CLEAR_OVERRIDE = "clear_override"
SERVICE_SWITCH_SCHEDULE = "switch_schedule"
SERVICE_REFRESH_SCHEDULES = "refresh_schedules"
SERVICE_SET_SCHEDULE_SLOT = "set_schedule_slot"

# Service attributes
ATTR_ROOM_ID = "room_id"
ATTR_SCHEDULE_NAME = "schedule_name"
ATTR_DAY = "day"  # Legacy, kept for backward compatibility
ATTR_START_DAY = "start_day"
ATTR_END_DAY = "end_day"
ATTR_START_TIME = "start_time"
ATTR_END_TIME = "end_time"
ATTR_ZONE_NAME = "zone_name"

# Base service schemas (dynamic schemas are built in async_register_services)
CLEAR_OVERRIDE_SCHEMA = vol.Schema({vol.Required(ATTR_ROOM_ID): str})
REFRESH_SCHEDULES_SCHEMA = vol.Schema({})


async def async_generate_services_yaml(hass: HomeAssistant, intuis_home: IntuisHome) -> None:
    """Generate services.yaml with dynamic options from API data.

    This allows the Home Assistant UI to show dropdown lists populated
    with actual schedule and zone names from the user's Intuis account.
    """
    # Collect schedule names (only home-level schedules with zones and timetables)
    schedule_names: list[str] = []
    zone_names: list[str] = []

    # Log all schedules for debugging
    _LOGGER.debug("=== All schedules from API ===")
    for schedule in intuis_home.schedules:
        if isinstance(schedule, IntuisThermSchedule):
            zone_count = len(schedule.zones) if schedule.zones else 0
            timetable_count = len(schedule.timetables) if schedule.timetables else 0
            # Count total rooms_temp across all zones
            rooms_temp_count = sum(
                len(z.rooms_temp) for z in schedule.zones
                if isinstance(z, IntuisThermZone) and z.rooms_temp
            ) if schedule.zones else 0
            _LOGGER.debug(
                "Schedule: '%s' (ID: %s) - zones: %d, timetables: %d, rooms_temp: %d, selected: %s, default: %s",
                schedule.name, schedule.id, zone_count, timetable_count, rooms_temp_count,
                schedule.selected, schedule.default
            )

    for schedule in intuis_home.schedules:
        if isinstance(schedule, IntuisThermSchedule):
            # Only include schedules that have zones defined (home-level schedules)
            has_zones = schedule.zones and len(schedule.zones) > 0
            has_timetables = schedule.timetables and len(schedule.timetables) > 0

            if has_zones and has_timetables:
                schedule_names.append(schedule.name)
                if schedule.selected:
                    # Get zones from active schedule
                    for zone in schedule.zones:
                        if isinstance(zone, IntuisThermZone):
                            zone_names.append(zone.name)

    # Build day options with French labels
    day_options = [
        {"label": day_fr, "value": str(i)}
        for i, day_fr in enumerate(DAYS_OF_WEEK_FR)
    ]

    # Build schedule options
    schedule_options = [{"label": name, "value": name} for name in schedule_names]
    if not schedule_options:
        schedule_options = [{"label": "No schedules found", "value": ""}]

    # Build zone options
    zone_options = [{"label": name, "value": name} for name in zone_names]
    if not zone_options:
        zone_options = [{"label": "No zones found", "value": ""}]

    # Build services.yaml content
    services_config = {
        "switch_schedule": {
            "name": "Switch Schedule",
            "description": "Switch to a different heating schedule. The schedule applies to all rooms in the home.",
            "fields": {
                "schedule_name": {
                    "name": "Schedule Name",
                    "description": "Select the schedule to activate.",
                    "required": True,
                    "selector": {
                        "select": {
                            "options": schedule_options,
                        }
                    }
                }
            }
        },
        "refresh_schedules": {
            "name": "Refresh Schedules",
            "description": "Force a refresh of all schedule and home data from the Intuis API.",
        },
        "set_schedule_slot": {
            "name": "Set Schedule Slot",
            "description": "Set a zone for a specific time range in the active heating schedule. Creates a slot from start_time to end_time with the specified zone.",
            "fields": {
                "day": {
                    "name": "Day of Week",
                    "description": "Select the day of the week.",
                    "required": True,
                    "selector": {
                        "select": {
                            "options": day_options,
                        }
                    }
                },
                "start_time": {
                    "name": "Start Time",
                    "description": "When the zone should start (24-hour format).",
                    "required": True,
                    "example": "08:00",
                    "selector": {
                        "time": None
                    }
                },
                "end_time": {
                    "name": "End Time",
                    "description": "When the zone should end.",
                    "required": True,
                    "example": "22:00",
                    "selector": {
                        "time": None
                    }
                },
                "zone_name": {
                    "name": "Zone Name",
                    "description": "Select the zone to apply.",
                    "required": True,
                    "selector": {
                        "select": {
                            "options": zone_options,
                        }
                    }
                }
            }
        }
    }

    # Write to services.yaml using async I/O
    services_yaml_path = Path(__file__).parent / "services.yaml"
    yaml_content = yaml.dump(services_config, default_flow_style=False, allow_unicode=True, sort_keys=False)

    def write_file() -> None:
        with open(services_yaml_path, "w", encoding="utf-8") as f:
            f.write(yaml_content)

    try:
        await hass.async_add_executor_job(write_file)
        _LOGGER.info(
            "Generated services.yaml with %d schedules and %d zones",
            len(schedule_names),
            len(zone_names),
        )
    except OSError as err:
        _LOGGER.error("Failed to generate services.yaml: %s", err)


async def async_register_services(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register Intuis Connect services."""

    async def async_handle_switch_schedule(call: ServiceCall) -> None:
        """Handle switch_schedule service call."""
        schedule_name = call.data.get(ATTR_SCHEDULE_NAME)

        if not schedule_name:
            _LOGGER.error("schedule_name must be provided")
            return

        # Get the first (and usually only) config entry
        for entry_id, data in hass.data[DOMAIN].items():
            if not isinstance(data, dict):
                continue

            api: IntuisAPI = data.get("api")
            intuis_home: IntuisHome = data.get("intuis_home")
            coordinator = data.get("coordinator")

            if not api or not intuis_home:
                continue

            # Find the schedule by name
            target_schedule = None
            available_schedules = []
            for schedule in intuis_home.schedules:
                if isinstance(schedule, IntuisThermSchedule):
                    available_schedules.append(schedule.name)
                    if schedule.name == schedule_name:
                        target_schedule = schedule
                        break

            if not target_schedule:
                _LOGGER.error(
                    "Schedule not found: %s. Available schedules: %s",
                    schedule_name,
                    available_schedules
                )
                return

            _LOGGER.info(
                "Switching to schedule: %s (ID: %s)",
                target_schedule.name,
                target_schedule.id
            )

            try:
                await api.async_switch_schedule(intuis_home.id, target_schedule.id)
                # Update local state
                for s in intuis_home.schedules:
                    if isinstance(s, IntuisThermSchedule):
                        s.selected = (s.id == target_schedule.id)
                # Refresh coordinator
                if coordinator:
                    await coordinator.async_request_refresh()
            except Exception as err:
                _LOGGER.error("Failed to switch schedule: %s", err)
                raise

            break

    async def async_handle_refresh_schedules(call: ServiceCall) -> None:
        """Handle refresh_schedules service call.

        This fetches fresh schedule data from the Intuis API and updates
        the local state, then regenerates services.yaml with updated options.
        """
        for entry_id, data in hass.data[DOMAIN].items():
            if not isinstance(data, dict):
                continue

            api: IntuisAPI = data.get("api")
            intuis_home: IntuisHome = data.get("intuis_home")
            coordinator = data.get("coordinator")

            if not api or not intuis_home:
                continue

            _LOGGER.info("Fetching fresh schedule data from Intuis API")

            try:
                # Fetch fresh homes data (includes schedules) from the API
                fresh_home = await api.async_get_homes_data()

                # Update local schedules from fresh data
                intuis_home.schedules = fresh_home.schedules

                _LOGGER.info(
                    "Refreshed %d schedules from Intuis API",
                    len(fresh_home.schedules),
                )

                # Regenerate services.yaml with updated schedule/zone options
                await async_generate_services_yaml(hass, intuis_home)

                # Also trigger coordinator refresh for room status
                if coordinator:
                    await coordinator.async_request_refresh()

            except Exception as err:
                _LOGGER.error("Failed to refresh schedules from API: %s", err)
                raise

            break

    async def async_handle_set_schedule_slot(call: ServiceCall) -> None:
        """Handle set_schedule_slot service call.

        Sets a zone for a specific time range in the active schedule.
        Supports multi-day spans with start_day and end_day parameters.
        Creates two timetable entries: one at start_time with the target zone,
        and one at end_time to restore the previous zone.
        """
        # Support both legacy 'day' and new 'start_day'/'end_day' parameters
        start_day_str = call.data.get(ATTR_START_DAY) or call.data.get(ATTR_DAY)
        end_day_str = call.data.get(ATTR_END_DAY) or call.data.get(ATTR_DAY)
        start_time = call.data.get(ATTR_START_TIME)
        end_time = call.data.get(ATTR_END_TIME)
        zone_name = call.data.get(ATTR_ZONE_NAME)

        if not zone_name:
            _LOGGER.error("zone_name must be provided")
            return

        # Convert start_day from string to int
        try:
            start_day = int(start_day_str)
            if not (0 <= start_day <= 6):
                raise ValueError("start_day must be between 0 and 6")
        except (ValueError, TypeError):
            _LOGGER.error("Invalid start_day value: %s (expected 0-6)", start_day_str)
            return

        # Convert end_day from string to int
        try:
            end_day = int(end_day_str)
            if not (0 <= end_day <= 6):
                raise ValueError("end_day must be between 0 and 6")
        except (ValueError, TypeError):
            _LOGGER.error("Invalid end_day value: %s (expected 0-6)", end_day_str)
            return

        # Parse start_time (TimeSelector returns HH:MM:SS string or dict)
        try:
            if isinstance(start_time, dict):
                start_hours = start_time.get("hours", 0)
                start_minutes = start_time.get("minutes", 0)
            else:
                # Handle HH:MM or HH:MM:SS format
                parts = str(start_time).split(":")
                start_hours = int(parts[0])
                start_minutes = int(parts[1]) if len(parts) > 1 else 0
            if not (0 <= start_hours <= 23 and 0 <= start_minutes <= 59):
                raise ValueError("Invalid start time")
        except (ValueError, AttributeError, TypeError) as e:
            _LOGGER.error("Invalid start_time format: %s (%s)", start_time, e)
            return

        # Parse end_time (TimeSelector returns HH:MM:SS string or dict)
        # Special case: 00:00 means end of day (midnight)
        try:
            if isinstance(end_time, dict):
                end_hours = end_time.get("hours", 0)
                end_minutes = end_time.get("minutes", 0)
            else:
                # Handle HH:MM or HH:MM:SS format
                parts = str(end_time).split(":")
                end_hours = int(parts[0])
                end_minutes = int(parts[1]) if len(parts) > 1 else 0
            if not (0 <= end_hours <= 23 and 0 <= end_minutes <= 59):
                raise ValueError("Invalid end time")
        except (ValueError, AttributeError, TypeError) as e:
            _LOGGER.error("Invalid end_time format: %s (%s)", end_time, e)
            return

        # Calculate m_offsets (minutes from Monday 00:00)
        start_m_offset = start_day * MINUTES_PER_DAY + start_hours * 60 + start_minutes

        # For end offset: handle 00:00 (midnight) specially
        # - Same day with 00:00 end: means "end of that day" = start of next day
        # - Different day with 00:00: means "start of that day" (the midnight boundary)
        if end_hours == 0 and end_minutes == 0 and start_day == end_day:
            # Same day, 00:00 means end of that day (next day's 00:00)
            end_m_offset = (end_day + 1) * MINUTES_PER_DAY
        else:
            # Different day or non-midnight: calculate normally
            end_m_offset = end_day * MINUTES_PER_DAY + end_hours * 60 + end_minutes

        # Validate that end is after start (considering week wrap)
        # For multi-day spans, end_m_offset might be less if wrapping around the week
        if start_day == end_day and end_m_offset <= start_m_offset:
            _LOGGER.error(
                "end_time (%s) must be after start_time (%s) on the same day",
                end_time,
                start_time,
            )
            return

        for entry_id, data in hass.data[DOMAIN].items():
            if not isinstance(data, dict):
                continue

            api: IntuisAPI = data.get("api")
            intuis_home: IntuisHome = data.get("intuis_home")
            coordinator = data.get("coordinator")

            if not api or not intuis_home:
                continue

            # Find the active therm schedule
            active_schedule = None
            for schedule in intuis_home.schedules:
                if isinstance(schedule, IntuisThermSchedule) and schedule.selected:
                    active_schedule = schedule
                    break

            if not active_schedule:
                _LOGGER.error("No active therm schedule found")
                return

            # Find the target zone by name
            target_zone = None
            available_zones = []
            for zone in active_schedule.zones:
                if isinstance(zone, IntuisThermZone):
                    available_zones.append(zone.name)
                    if zone.name.lower() == zone_name.lower():
                        target_zone = zone
                        break

            if not target_zone:
                _LOGGER.error(
                    "Zone not found: %s. Available zones: %s",
                    zone_name,
                    available_zones,
                )
                return

            if start_day == end_day:
                _LOGGER.info(
                    "Setting zone '%s' (ID: %d) on %s from %s to %s",
                    target_zone.name,
                    target_zone.id,
                    DAYS_OF_WEEK[start_day],
                    start_time,
                    end_time,
                )
            else:
                _LOGGER.info(
                    "Setting zone '%s' (ID: %d) from %s %s to %s %s",
                    target_zone.name,
                    target_zone.id,
                    DAYS_OF_WEEK[start_day],
                    start_time,
                    DAYS_OF_WEEK[end_day],
                    end_time,
                )

            # Build updated timetable
            timetable = [
                {"zone_id": t.zone_id, "m_offset": t.m_offset}
                for t in active_schedule.timetables
            ]

            # Find which zone is active at end_time (to restore after the slot ends)
            # We look at end_m_offset to find what zone was scheduled there originally
            restore_zone_id = find_zone_at_offset(timetable, end_m_offset)

            # Insert/update start entry with target zone
            upsert_timetable_entry(timetable, start_m_offset, target_zone.id)

            # Insert/update end entry to restore previous zone
            upsert_timetable_entry(timetable, end_m_offset, restore_zone_id)

            # Sort and remove consecutive duplicates (API requirement)
            timetable = remove_consecutive_duplicates(timetable)

            _LOGGER.debug(
                "Timetable after update: %s",
                [(t["m_offset"], t["zone_id"]) for t in timetable],
            )

            # Build zones payload (only rooms_temp, not rooms - API requirement)
            zones_payload = []
            for zone in active_schedule.zones:
                if isinstance(zone, IntuisThermZone):
                    zone_data = {
                        "id": zone.id,
                        "name": zone.name,
                        "type": zone.type,
                        "rooms_temp": [
                            {"room_id": rt.room_id, "temp": rt.temp}
                            for rt in zone.rooms_temp
                        ],
                    }
                    zones_payload.append(zone_data)

            try:
                await api.async_sync_schedule(
                    schedule_id=active_schedule.id,
                    schedule_name=active_schedule.name,
                    schedule_type=active_schedule.type,
                    timetable=timetable,
                    zones=zones_payload,
                    away_temp=active_schedule.away_temp,
                    hg_temp=active_schedule.hg_temp,
                )

                # Update local timetable state
                active_schedule.timetables = [
                    IntuisTimetable(zone_id=t["zone_id"], m_offset=t["m_offset"])
                    for t in timetable
                ]

                # Refresh coordinator
                if coordinator:
                    await coordinator.async_request_refresh()

                _LOGGER.info("Schedule slot updated successfully")

            except Exception as err:
                _LOGGER.error("Failed to set schedule slot: %s", err)
                raise

            break

    # Build dynamic options from coordinator data
    intuis_home: IntuisHome = hass.data[DOMAIN][entry.entry_id].get("intuis_home")

    schedule_options: list[dict] = []
    zone_options: list[dict] = []

    if intuis_home:
        for schedule in intuis_home.schedules:
            if isinstance(schedule, IntuisThermSchedule):
                schedule_options.append({
                    "value": schedule.name,
                    "label": schedule.name,
                })
                if schedule.selected:
                    # Get zones from active schedule
                    for zone in schedule.zones:
                        if isinstance(zone, IntuisThermZone):
                            zone_options.append({
                                "value": zone.name,
                                "label": zone.name,
                            })

    _LOGGER.debug("Dynamic schedule options: %s", schedule_options)
    _LOGGER.debug("Dynamic zone options: %s", zone_options)

    # Day options with French labels
    day_options = [
        {"value": "0", "label": "Lundi"},
        {"value": "1", "label": "Mardi"},
        {"value": "2", "label": "Mercredi"},
        {"value": "3", "label": "Jeudi"},
        {"value": "4", "label": "Vendredi"},
        {"value": "5", "label": "Samedi"},
        {"value": "6", "label": "Dimanche"},
    ]

    # Build dynamic schemas with SelectSelector for proper dropdown UI
    switch_schedule_schema = vol.Schema({
        vol.Required(ATTR_SCHEDULE_NAME): SelectSelector(
            SelectSelectorConfig(
                options=schedule_options if schedule_options else [{"value": "", "label": "No schedules found"}],
                mode=SelectSelectorMode.DROPDOWN,
            )
        ),
    })

    set_schedule_slot_schema = vol.Schema({
        vol.Required(ATTR_START_DAY): SelectSelector(
            SelectSelectorConfig(
                options=day_options,
                mode=SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Required(ATTR_START_TIME): TimeSelector(TimeSelectorConfig()),
        vol.Required(ATTR_END_DAY): SelectSelector(
            SelectSelectorConfig(
                options=day_options,
                mode=SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Required(ATTR_END_TIME): TimeSelector(TimeSelectorConfig()),
        vol.Required(ATTR_ZONE_NAME): SelectSelector(
            SelectSelectorConfig(
                options=zone_options if zone_options else [{"value": "", "label": "No zones found"}],
                mode=SelectSelectorMode.DROPDOWN,
            )
        ),
    })

    # Register services (only once)
    if not hass.services.has_service(DOMAIN, SERVICE_SWITCH_SCHEDULE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SWITCH_SCHEDULE,
            async_handle_switch_schedule,
            schema=switch_schedule_schema,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_REFRESH_SCHEDULES):
        hass.services.async_register(
            DOMAIN,
            SERVICE_REFRESH_SCHEDULES,
            async_handle_refresh_schedules,
            schema=REFRESH_SCHEDULES_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_SET_SCHEDULE_SLOT):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_SCHEDULE_SLOT,
            async_handle_set_schedule_slot,
            schema=set_schedule_slot_schema,
        )
