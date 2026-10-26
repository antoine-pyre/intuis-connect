"""Schedule contracts at real registered services and number entry points."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.intuis_connect.entity.intuis_schedule import IntuisSchedule
from custom_components.intuis_connect.intuis_api.api import APIError
from custom_components.intuis_connect.number import IntuisZoneTemperatureNumber
from custom_components.intuis_connect.services import async_register_services
from custom_components.intuis_connect.timetable import (
    MINUTES_PER_WEEK,
    replace_timetable_interval,
    schedule_slot_offsets,
)
from custom_components.intuis_connect.utils.const import DOMAIN


ORIGINAL = [
    {"m_offset": 0, "zone_id": 1},
    {"m_offset": 480, "zone_id": 2},
    {"m_offset": 600, "zone_id": 1},
    {"m_offset": 1440, "zone_id": 2},
    {"m_offset": 7000, "zone_id": 1},
    {"m_offset": 9800, "zone_id": 2},
]


def week_values(timetable):
    """Expand specified segments, independently of the production lookup helper."""
    ordered = sorted(timetable, key=lambda t: t["m_offset"])
    values = [ordered[-1]["zone_id"]] * MINUTES_PER_WEEK
    for index, entry in enumerate(ordered):
        end = (
            ordered[index + 1]["m_offset"]
            if index + 1 < len(ordered)
            else MINUTES_PER_WEEK
        )
        values[entry["m_offset"] : end] = [entry["zone_id"]] * (end - entry["m_offset"])
    return values


@pytest.mark.parametrize(
    "timetable,start,end",
    [
        (ORIGINAL, 420, 660),
        (ORIGINAL, 480, 600),
        (ORIGINAL, 1320, 1800),
        (ORIGINAL, 7080, 360),
        (ORIGINAL, 6 * 1440 + 22 * 60, 10080),
        (ORIGINAL, 0, 360),
        (ORIGINAL[1:], 30, 400),
        (ORIGINAL[1:], 9900, 100),
        ([{"m_offset": 500, "zone_id": 1}], 400, 900),
    ],
)
def test_interval_changes_only_the_requested_minutes(timetable, start, end):
    before = deepcopy(timetable)
    expected = week_values(timetable)
    if start < end:
        expected[start:end] = [3] * (end - start)
    else:
        expected[start:] = [3] * (MINUTES_PER_WEEK - start)
        expected[:end] = [3] * end
    result = replace_timetable_interval(timetable, start, end, 3)
    assert (
        week_values(result) == expected
    )  # Check every minute, including the end boundary.
    assert timetable == before
    assert all(0 <= t["m_offset"] < MINUTES_PER_WEEK for t in result)
    assert all(a["zone_id"] != b["zone_id"] for a, b in zip(result, result[1:]))


@pytest.mark.parametrize(
    "start,end", [(0, 0), (-1, 50), (0, 10081), (10080, 50), (1.5, 40), (True, 40)]
)
def test_ambiguous_or_invalid_offsets_rejected(start, end):
    with pytest.raises(ValueError):
        replace_timetable_interval(ORIGINAL, start, end, 3)


@pytest.mark.parametrize(
    "args,expected",
    [
        (("0", "18:00", "0", "00:00"), (1080, 1440)),
        (("6", "22:00", "6", "00:00"), (9960, 10080)),
        (("4", "22:00:00", "0", "06:00:00"), (7080, 360)),
        ((0, {"hours": 7, "minutes": 30}, 1, "00:00"), (450, 1440)),
    ],
)
def test_service_offsets_keep_midnight_and_week_wrap_semantics(args, expected):
    assert schedule_slot_offsets(*args) == expected


@pytest.mark.parametrize(
    "args",
    [
        (0, "07:00", 0, "07:00"),
        (0, "22:00", 0, "08:00"),
        (7, "07:00", 0, "08:00"),
        (0, "24:00", 1, "08:00"),
        (0, "07:00:01", 1, "08:00"),
        (0, "07:60", 1, "08:00"),
    ],
)
def test_invalid_service_intervals_rejected(args):
    with pytest.raises(ValueError):
        schedule_slot_offsets(*args)


def make_schedule():
    return IntuisSchedule.from_dict(
        {
            "id": "schedule",
            "name": "Week",
            "type": "therm",
            "selected": True,
            "away_temp": 16,
            "hg_temp": 7,
            "timetable": deepcopy(ORIGINAL),
            "zones": [
                {
                    "id": index,
                    "name": name,
                    "type": 0,
                    "rooms_temp": [{"room_id": "room", "temp": 20.0}],
                }
                for index, name in [(1, "Night"), (2, "Comfort"), (3, "Eco")]
            ],
        }
    )


@pytest.fixture
async def schedule_services(ha_hass, ha_entry_factory):
    entry = ha_entry_factory()
    home = SimpleNamespace(
        id="home",
        name="Home",
        schedules=[make_schedule()],
        rooms={"room": SimpleNamespace(name="Room")},
    )
    api = SimpleNamespace(async_sync_schedule=AsyncMock(), _schedule_mutation_locks={})
    coordinator = MagicMock(
        data={"intuis_home": home}, async_request_refresh=AsyncMock()
    )
    data = {"api": api, "intuis_home": home, "coordinator": coordinator}
    ha_hass.data[DOMAIN] = {entry.entry_id: data}
    await async_register_services(ha_hass, entry)
    return SimpleNamespace(
        hass=ha_hass, api=api, home=home, coordinator=coordinator, data=data
    )


async def call(h, service, **kwargs):
    await h.hass.services.async_call(DOMAIN, service, kwargs, blocking=True)


def slot_args(**kwargs):
    return {
        "start_day": "0",
        "end_day": "0",
        "start_time": "07:00",
        "end_time": "11:00",
        "zone_name": "Eco",
        **kwargs,
    }


def temp_args(**kwargs):
    return {
        "schedule_name": "Week",
        "zone_name": "Eco",
        "room_name": "Room",
        "temperature": 19.5,
        **kwargs,
    }


def number(h, zone_index=2):
    schedule = h.home.schedules[0]
    zone = schedule.zones[zone_index]
    entity = IntuisZoneTemperatureNumber(
        h.coordinator, h.api, "home", schedule, zone, zone.rooms_temp[0], "Room"
    )
    entity.hass = h.hass
    entity.async_write_ha_state = MagicMock()
    return entity


def snapshot(schedule):
    return {
        "timetable": [vars(t).copy() for t in schedule.timetables],
        "zones": [
            [(rt.room_id, rt.temp) for rt in z.rooms_temp] for z in schedule.zones
        ],
    }


async def test_registered_slot_service_removes_internal_transitions(schedule_services):
    h = schedule_services
    await call(h, "set_schedule_slot", **slot_args())
    sent = h.api.async_sync_schedule.call_args.kwargs["timetable"]
    assert not any(t["m_offset"] in (480, 600) for t in sent)
    assert week_values(sent)[420:660] == [3] * 240
    assert week_values(sent)[660] == 1
    assert snapshot(h.home.schedules[0])["timetable"] == sent
    h.coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"start_day": "4", "end_day": "0", "start_time": "22:00", "end_time": "06:00"},
        {"start_day": "6", "end_day": "6", "start_time": "22:00", "end_time": "00:00"},
    ],
)
async def test_registered_slot_service_handles_week_wrap(schedule_services, kwargs):
    h = schedule_services
    await call(h, "set_schedule_slot", **slot_args(**kwargs))
    sent = h.api.async_sync_schedule.call_args.kwargs["timetable"]
    assert all(0 <= t["m_offset"] < 10080 for t in sent)
    assert week_values(sent)[10000] == 3
    if kwargs["start_day"] == "4":
        assert week_values(sent)[0:360] == [3] * 360
        assert week_values(sent)[360] == 1
    else:
        assert week_values(sent)[0] == 1


async def test_registered_slot_accepts_legacy_day(schedule_services):
    h = schedule_services
    args = slot_args()
    del args["start_day"], args["end_day"]
    await call(h, "set_schedule_slot", **args, day="0")
    h.api.async_sync_schedule.assert_awaited_once()


@pytest.mark.parametrize("entrypoint", ["service", "number"])
async def test_half_degree_temperature_is_preserved(schedule_services, entrypoint):
    h = schedule_services
    if entrypoint == "service":
        await call(h, "set_zone_temperature", **temp_args())
    else:
        entity = number(h)
        await entity.async_set_native_value(19.5)
        assert entity.native_value == 19.5
    assert h.home.schedules[0].zones[2].rooms_temp[0].temp == 19.5
    assert (
        h.api.async_sync_schedule.call_args.kwargs["zones"][2]["rooms_temp"][0]["temp"]
        == 19.5
    )


@pytest.mark.parametrize("entrypoint", ["slot", "temperature", "number"])
async def test_api_failure_preserves_confirmed_schedule(schedule_services, entrypoint):
    h = schedule_services
    before = snapshot(h.home.schedules[0])
    h.api.async_sync_schedule.side_effect = APIError("refused")
    with pytest.raises(APIError):
        if entrypoint == "slot":
            await call(h, "set_schedule_slot", **slot_args())
        elif entrypoint == "temperature":
            await call(h, "set_zone_temperature", **temp_args())
        else:
            entity = number(h)
            await entity.async_set_native_value(19.5)
    assert snapshot(h.home.schedules[0]) == before
    h.coordinator.async_request_refresh.assert_not_awaited()


@pytest.mark.parametrize("value", [19.25, float("nan"), float("inf"), 4.5, 30.5, True])
async def test_number_rejects_invalid_temperature_before_api(schedule_services, value):
    h = schedule_services
    with pytest.raises(ServiceValidationError):
        await number(h).async_set_native_value(value)
    h.api.async_sync_schedule.assert_not_awaited()


async def test_service_rejects_fractional_step_before_api(schedule_services):
    h = schedule_services
    with pytest.raises(ServiceValidationError):
        await call(h, "set_zone_temperature", **temp_args(temperature=19.25))
    h.api.async_sync_schedule.assert_not_awaited()


async def test_service_and_number_serialize_and_resolve_fresh_models(schedule_services):
    h = schedule_services
    entity = number(h, zone_index=1)
    entered, release = asyncio.Event(), asyncio.Event()
    sent = []

    async def sync(**payload):
        sent.append(deepcopy(payload))
        if len(sent) == 1:
            entered.set()
            await release.wait()

    h.api.async_sync_schedule.side_effect = sync
    first = asyncio.create_task(
        call(h, "set_zone_temperature", **temp_args(temperature=21.5))
    )
    await entered.wait()
    second = asyncio.create_task(entity.async_set_native_value(19.5))
    await asyncio.sleep(0)
    assert len(sent) == 1
    # A refresh replaces the model while the first request is in flight.
    h.home.schedules = [make_schedule()]
    release.set()
    await first
    await second
    assert sent[1]["zones"][2]["rooms_temp"][0]["temp"] == 21.5
    assert sent[1]["zones"][1]["rooms_temp"][0]["temp"] == 19.5
    assert h.home.schedules[0].zones[2].rooms_temp[0].temp == 21.5
    assert entity.native_value == 19.5
