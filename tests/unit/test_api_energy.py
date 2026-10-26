"""Regressions for the real HTTP client and per-room energy availability."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest
from aioresponses import CallbackResult

from custom_components.intuis_connect.entity.intuis_home_entity import IntuisHomeEnergySensor
from custom_components.intuis_connect.intuis_api.api import (
    APIError, CannotConnect, EnergyDataUnavailable, IntuisAPI, InvalidAuth, RateLimitError,
)
from custom_components.intuis_connect.intuis_data import IntuisData
from custom_components.intuis_connect.sensor import IntuisEnergySensor
from custom_components.intuis_connect.utils.const import AUTH_PATH, BASE_URLS, ROOMMEASURE_PATH


@pytest.fixture
def no_backoff(monkeypatch):
    """Remove retry delays without replacing ClientResponse semantics."""
    sleep = AsyncMock()
    monkeypatch.setattr("custom_components.intuis_connect.intuis_api.api.asyncio.sleep", sleep)
    return sleep


def client(session):
    api = IntuisAPI(session, home_id="home", min_request_delay=0, rate_limit_delay=0)
    api._access_token = "old-access"
    api.refresh_token = "test-refresh"
    return api


@pytest.mark.parametrize("payload", [{"json": {"temperature": 19.5}}, {"data": {"room": "room-a"}}])
async def test_retry_401_preserves_complete_request(cloud_responses, payload):
    url = "https://energy.invalid/api/schedule?home_id=home&schedule_id=42"
    seen = []

    def endpoint(url, **kwargs):
        seen.append(kwargs)
        return CallbackResult(status=401 if len(seen) == 1 else 200, payload={"ok": True})

    cloud_responses.post(url, callback=endpoint, repeat=True)
    cloud_responses.post(BASE_URLS[0] + AUTH_PATH, payload={"access_token": "new-access", "refresh_token": "new-refresh"})
    headers = {"X-Intuis-Test": "specific"}
    async with aiohttp.ClientSession() as session:
        api = client(session)
        async with await api._async_request(
            "post", "/api/schedule", full_url=url, timeout=7, headers=headers, **payload
        ) as response:
            assert await response.json() == {"ok": True}
    assert len(seen) == 2
    assert headers == {"X-Intuis-Test": "specific"}
    for request in seen:
        assert request["timeout"] == 7
        assert request["headers"]["X-Intuis-Test"] == "specific"
        for key, value in payload.items():
            assert request[key] == value
    assert seen[0]["headers"]["Authorization"] == "Bearer old-access"
    assert seen[1]["headers"]["Authorization"] == "Bearer new-access"
    assert len(cloud_responses.requests) == 2  # exactly the original URL plus auth


async def test_repeated_401_refreshes_only_once(cloud_responses):
    url = BASE_URLS[0] + "/test"
    auth = BASE_URLS[0] + AUTH_PATH
    cloud_responses.get(url, status=401, repeat=True)
    cloud_responses.post(auth, payload={"access_token": "new"}, repeat=True)
    async with aiohttp.ClientSession() as session:
        with pytest.raises(InvalidAuth, match="after token refresh"):
            await client(session)._async_request("get", "/test")
    requests = {str(key[1]): len(calls) for key, calls in cloud_responses.requests.items()}
    assert requests == {url: 2, auth: 1}


@pytest.mark.parametrize("refresh", ["refused", "timeout"])
async def test_refresh_failure_is_explicit_and_not_looped(cloud_responses, refresh):
    cloud_responses.get(BASE_URLS[0] + "/test", status=401, repeat=True)
    auth = BASE_URLS[0] + AUTH_PATH
    if refresh == "refused":
        cloud_responses.post(auth, status=400, repeat=True)
        error = InvalidAuth
    else:
        cloud_responses.post(auth, exception=asyncio.TimeoutError(), repeat=True)
        error = CannotConnect
    async with aiohttp.ClientSession() as session:
        with pytest.raises(error):
            await client(session)._async_request("get", "/test")
    assert all(len(calls) == 1 for calls in cloud_responses.requests.values())


@pytest.mark.parametrize("status", [429, 500])
async def test_transient_http_error_retries_real_response(cloud_responses, no_backoff, status):
    url = BASE_URLS[0] + "/test"
    cloud_responses.get(url, status=status, headers={"Retry-After": "0"})
    cloud_responses.get(url, payload={"ok": True})
    async with aiohttp.ClientSession() as session:
        async with await client(session)._async_request("get", "/test") as response:
            assert await response.json() == {"ok": True}
    assert no_backoff.await_count == 1


@pytest.mark.parametrize("kind,error", [("429", RateLimitError), ("500", APIError), ("timeout", CannotConnect)])
async def test_exhausted_retries_raise_typed_error(cloud_responses, no_backoff, kind, error):
    if kind == "timeout":
        cloud_responses.get(BASE_URLS[0] + "/test", exception=asyncio.TimeoutError(), repeat=True)
    else:
        cloud_responses.get(BASE_URLS[0] + "/test", status=int(kind), repeat=True)
    async with aiohttp.ClientSession() as session:
        with pytest.raises(error):
            await client(session)._async_request("get", "/test")


@pytest.mark.parametrize("body,error", [
    ({"body": []}, EnergyDataUnavailable),
    ({"body": [{"value": [[None, None]]}]}, EnergyDataUnavailable),
    ({"error": {"message": "failed"}}, APIError),
    ({"body": "malformed"}, APIError),
    ({"body": [{"value": [[float("nan")]]}]}, APIError),
    ({"body": [{"value": [[-5]]}]}, APIError),
    ({"body": [{"value": [["bad"]]}]}, APIError),
])
async def test_energy_errors_never_become_zero(cloud_responses, body, error):
    cloud_responses.post(BASE_URLS[0] + ROOMMEASURE_PATH, payload=body)
    async with aiohttp.ClientSession() as session:
        with pytest.raises(error):
            await client(session)._async_get_room_energy("room", 0, 86400)


async def test_bulk_results_preserve_zero_and_omit_failed_or_missing_rooms(cloud_responses):
    def endpoint(url, **kwargs):
        room = kwargs["data"]["room_id"]
        if room == "failed":
            return CallbackResult(status=400, reason="Bad request")
        if room == "missing":
            return CallbackResult(payload={"body": []})
        return CallbackResult(payload={"body": [{"value": [[0, None]]}]})
    cloud_responses.post(BASE_URLS[0] + ROOMMEASURE_PATH, callback=endpoint, repeat=True)
    async with aiohttp.ClientSession() as session:
        result = await client(session).async_get_energy_measures(
            [{"id": room, "bridge": "b"} for room in ["zero", "failed", "missing"]], 0, 86400
        )
    assert result == {"zero": 0.0}


async def test_daily_series_preserves_gaps_and_zeroes(cloud_responses):
    cloud_responses.post(BASE_URLS[0] + ROOMMEASURE_PATH, payload={"body": [
        {"beg_time": 0, "step_time": 86400, "value": [[0, None], [None, None], [120, 30]]}
    ]})
    async with aiohttp.ClientSession() as session:
        result = await client(session).async_get_room_energy_daily("room", 0, 259200)
    assert result == [(0, 0.0), (172800, 150.0)]


async def test_daily_api_error_is_propagated_to_import_caller(cloud_responses):
    cloud_responses.post(BASE_URLS[0] + ROOMMEASURE_PATH, status=400)
    async with aiohttp.ClientSession() as session:
        with pytest.raises(APIError):
            await client(session).async_get_room_energy_daily("room", 0, 86400)


def room(room_id="room"):
    return SimpleNamespace(id=room_id, name=room_id, bridge_id="bridge", energy=None,
                           energy_day=None, energy_updated_at=None, energy_stale=True)


def data_handler(*results, scale="1day"):
    api = SimpleNamespace(home_timezone="Europe/Paris", async_get_energy_measures=AsyncMock(side_effect=results))
    data = IntuisData(api, SimpleNamespace(rooms={}), get_options=lambda: {"energy_scale": scale, "energy_reset_hour": 2})
    return data, api


async def fetch(data, rooms):
    await data._fetch_energy_data(rooms, datetime.now(timezone.utc))


async def test_daily_cache_retries_only_failed_rooms_and_accepts_zero(frozen_clock):
    data, api = data_handler({"a": 0.0}, {"b": 500.0})
    rooms = {"a": room("a"), "b": room("b")}
    await fetch(data, rooms)
    assert rooms["a"].energy == 0.0 and not rooms["a"].energy_stale
    assert rooms["b"].energy is None and rooms["b"].energy_stale
    # Mapper creates new room instances on each coordinator update.
    rooms = {"a": room("a"), "b": room("b")}
    await fetch(data, rooms)
    assert api.async_get_energy_measures.call_args.args[0] == [{"id": "b", "bridge": "bridge"}]
    assert rooms["a"].energy == 0.0 and rooms["b"].energy == 0.5
    assert all(not r.energy_stale for r in rooms.values())
    await fetch(data, rooms)
    assert api.async_get_energy_measures.await_count == 2


async def test_entire_fetch_failure_is_retried_next_cycle(frozen_clock):
    data, api = data_handler(CannotConnect("offline"), {"room": 1000.0})
    rooms = {"room": room()}
    await fetch(data, rooms)
    assert rooms["room"].energy is None
    await fetch(data, rooms)
    assert rooms["room"].energy == 1.0
    assert api.async_get_energy_measures.await_count == 2


async def test_realtime_retains_last_value_with_original_timestamp_and_stale_flag(frozen_clock):
    data, _ = data_handler({"room": 2400.0}, {}, scale="1hour")
    rooms = {"room": room()}
    await fetch(data, rooms)
    timestamp = rooms["room"].energy_updated_at
    frozen_clock.tick(120)
    await fetch(data, rooms)
    assert rooms["room"].energy == 2.4
    assert rooms["room"].energy_updated_at == timestamp
    assert rooms["room"].energy_stale


def sensor(rooms):
    coordinator = MagicMock(data={"rooms": rooms}, last_update_success=True)
    entity = IntuisEnergySensor(coordinator, "home", next(iter(rooms.values())))
    return entity, coordinator


async def test_initial_missing_sensor_unavailable_and_global_availability_preserved(frozen_clock):
    rooms = {"room": room()}
    entity, coordinator = sensor(rooms)
    assert entity.native_value is None and not entity.available
    data, _ = data_handler({"room": 0.0})
    await fetch(data, rooms)
    assert entity.native_value == 0.0 and entity.available
    assert not entity.extra_state_attributes["energy_stale"]
    coordinator.last_update_success = False
    assert not entity.available


async def test_failed_day_rollover_does_not_poison_new_daily_max(frozen_clock):
    data, _ = data_handler({"room": 5000.0}, {}, {"room": 400.0})
    rooms = {"room": room()}
    entity, _ = sensor(rooms)
    await fetch(data, rooms)
    assert entity.native_value == 5.0
    frozen_clock.move_to("2026-10-27 12:00:00")
    await fetch(data, rooms)
    assert entity.native_value == 5.0 and entity.extra_state_attributes["energy_stale"]
    assert entity.extra_state_attributes["measurement_day"] == "2026-10-26"
    await fetch(data, rooms)
    assert entity.native_value == 0.4 and not entity.extra_state_attributes["energy_stale"]


async def test_home_total_identifies_incomplete_measurements(frozen_clock):
    rooms = {"a": room("a"), "b": room("b")}
    coordinator = MagicMock(data={"rooms": rooms}, last_update_success=True)
    entity = IntuisHomeEnergySensor(coordinator, "home")
    data, _ = data_handler({"a": 1000.0}, {"b": 2000.0})
    await fetch(data, rooms)
    assert entity.native_value is None and not entity.available
    assert entity.extra_state_attributes["energy_stale"]
    assert entity.extra_state_attributes["room_breakdown"] == {"a": 1.0, "b": None}
    await fetch(data, rooms)
    assert entity.native_value == 3.0 and entity.available
    assert not entity.extra_state_attributes["energy_stale"]


async def test_daily_cache_uses_home_timezone_and_reset_boundary(frozen_clock):
    data, api = data_handler({"room": 2000.0}, {"room": 300.0})
    rooms = {"room": room()}
    await fetch(data, rooms)
    # Europe/Paris is UTC+1 here; 00:30 UTC is still before the 02:00 reset.
    frozen_clock.move_to("2026-10-27 00:30:00")
    await fetch(data, rooms)
    assert api.async_get_energy_measures.await_count == 1
    assert rooms["room"].energy_day == "2026-10-26"
    frozen_clock.move_to("2026-10-27 01:00:00")
    await fetch(data, rooms)
    assert api.async_get_energy_measures.await_count == 2
    assert rooms["room"].energy_day == "2026-10-27"
    assert rooms["room"].energy == 0.3
    # Query day starts at midnight in the home's zone, not the server zone.
    assert api.async_get_energy_measures.call_args.args[1] == int(
        datetime(2026, 10, 26, 23, tzinfo=timezone.utc).timestamp()
    )


async def test_home_keeps_last_complete_total_while_new_day_is_partial(frozen_clock):
    rooms = {"a": room("a"), "b": room("b")}
    coordinator = MagicMock(data={"rooms": rooms}, last_update_success=True)
    entity = IntuisHomeEnergySensor(coordinator, "home")
    data, _ = data_handler({"a": 2000.0, "b": 3000.0}, {"a": 300.0}, {"b": 400.0})
    await fetch(data, rooms)
    assert entity.native_value == 5.0
    frozen_clock.move_to("2026-10-27 12:00:00")
    await fetch(data, rooms)
    assert entity.native_value == 5.0
    assert entity.extra_state_attributes["energy_stale"]
    await fetch(data, rooms)
    assert entity.native_value == 0.7
    coordinator.last_update_success = False
    assert not entity.available
