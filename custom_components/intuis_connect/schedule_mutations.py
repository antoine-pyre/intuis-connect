"""Confirmed schedule mutations shared by services and number entities."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from copy import deepcopy
import math

from .entity.intuis_home import IntuisHome
from .entity.intuis_schedule import (
    IntuisThermSchedule,
    IntuisThermZone,
    IntuisTimetable,
)
from .intuis_api.api import IntuisAPI
from .timetable import replace_timetable_interval, remove_consecutive_duplicates


def validate_temperature(value: float) -> float:
    """Accept exactly the advertised half-degree range, without truncation."""
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 5 <= value <= 30
        or not float(value * 2).is_integer()
    ):
        raise ValueError(
            "Temperature must be finite, between 5 and 30 °C, in 0.5 °C steps"
        )
    return float(value)


def _schedule(home: IntuisHome, schedule_id: str) -> IntuisThermSchedule:
    for schedule in home.schedules:
        if isinstance(schedule, IntuisThermSchedule) and schedule.id == schedule_id:
            return schedule
    raise ValueError(f"Schedule {schedule_id} no longer exists")


async def _async_mutate(
    api: IntuisAPI,
    get_home: Callable[[], IntuisHome],
    schedule_id: str,
    mutation: Callable[[IntuisThermSchedule], None],
) -> None:
    # The API client is shared by service and number entry points. Its lock map
    # survives fresh model objects obtained by refresh_schedules.
    locks = api._schedule_mutation_locks
    async with locks.setdefault(schedule_id, asyncio.Lock()):
        proposed = deepcopy(_schedule(get_home(), schedule_id))
        mutation(proposed)
        await api.async_sync_schedule(
            schedule_id=proposed.id,
            schedule_name=proposed.name,
            schedule_type=proposed.type,
            timetable=[
                {"zone_id": t.zone_id, "m_offset": t.m_offset}
                for t in proposed.timetables
            ],
            zones=[
                {
                    "id": zone.id,
                    "name": zone.name,
                    "type": zone.type,
                    "rooms_temp": [
                        {"room_id": rt.room_id, "temp": rt.temp}
                        for rt in zone.rooms_temp
                    ],
                }
                for zone in proposed.zones
                if isinstance(zone, IntuisThermZone)
            ],
            away_temp=proposed.away_temp,
            hg_temp=proposed.hg_temp,
        )
        # Resolve again: a coordinator refresh may have replaced the models
        # while the network request was in flight. Never publish a stale object.
        current = _schedule(get_home(), schedule_id)
        current.timetables = proposed.timetables
        current.zones = proposed.zones
        current.away_temp = proposed.away_temp
        current.hg_temp = proposed.hg_temp


async def async_set_schedule_slot(
    api: IntuisAPI,
    get_home: Callable[[], IntuisHome],
    schedule_id: str,
    zone_name: str,
    start: int,
    end: int,
) -> None:
    def mutate(schedule):
        zone = next(
            (
                z
                for z in schedule.zones
                if isinstance(z, IntuisThermZone)
                and z.name.casefold() == zone_name.casefold()
            ),
            None,
        )
        if zone is None:
            raise ValueError(f"Zone {zone_name} not found in schedule {schedule.name}")
        timetable = replace_timetable_interval(
            [
                {"m_offset": t.m_offset, "zone_id": t.zone_id}
                for t in schedule.timetables
            ],
            start,
            end,
            zone.id,
        )
        schedule.timetables = [IntuisTimetable(**entry) for entry in timetable]

    await _async_mutate(api, get_home, schedule_id, mutate)


async def async_set_zone_temperature(
    api: IntuisAPI,
    get_home: Callable[[], IntuisHome],
    schedule_id: str,
    room_id: str,
    value: float,
    *,
    zone_id: int | None = None,
    zone_name: str | None = None,
) -> None:
    temperature = validate_temperature(value)

    def mutate(schedule):
        zone = next(
            (
                z
                for z in schedule.zones
                if isinstance(z, IntuisThermZone)
                and (
                    z.id == zone_id
                    if zone_id is not None
                    else zone_name is not None
                    and z.name.casefold() == zone_name.casefold()
                )
            ),
            None,
        )
        if zone is None:
            raise ValueError("Zone not found in the selected schedule")
        room = next((rt for rt in zone.rooms_temp if rt.room_id == room_id), None)
        if room is None:
            raise ValueError("Room not found in the selected zone")
        room.temp = temperature

    await _async_mutate(api, get_home, schedule_id, mutate)


async def async_sync_schedule(api, get_home, schedule_id, *, timetable=None,
                              away_temp=None, hg_temp=None):
    """Adapt TheFab21 #22/#24 full saves to the shared confirmed mutation path."""
    def mutate(schedule):
        if timetable is not None:
            zone_ids = {z.id for z in schedule.zones if isinstance(z, IntuisThermZone)}
            offsets = set()
            if not isinstance(timetable, list) or not 1 <= len(timetable) <= 512:
                raise ValueError("Timetable requires 1 to 512 transitions")
            for row in timetable:
                if (not isinstance(row, dict) or set(row) != {"m_offset", "zone_id"}
                        or type(row["m_offset"]) is not int
                        or not 0 <= row["m_offset"] < 10080
                        or row["m_offset"] in offsets
                        or type(row["zone_id"]) is not int
                        or row["zone_id"] not in zone_ids):
                    raise ValueError("Invalid timetable offset or unknown zone")
                offsets.add(row["m_offset"])
            schedule.timetables = [IntuisTimetable(**row) for row in
                                   remove_consecutive_duplicates(deepcopy(timetable))]
        for key, value, maximum in (("away_temp", away_temp, 25), ("hg_temp", hg_temp, 15)):
            if value is not None:
                temp = validate_temperature(value)
                if temp > maximum:
                    raise ValueError("Planning temperature out of range")
                setattr(schedule, key, temp)
    if timetable is None and away_temp is None and hg_temp is None:
        raise ValueError("No schedule changes supplied")
    await _async_mutate(api, get_home, schedule_id, mutate)
