"""Compatibility of actual entity IDs, entry data and storage across reloads."""

from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiohttp
import pytest
from homeassistant.config_entries import ConfigEntryState, current_entry
from homeassistant.helpers import device_registry as dr, entity_registry as er, frame
from homeassistant.helpers.storage import Store

from custom_components.intuis_connect import (
    async_migrate_entry,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.intuis_connect import climate, sensor
from custom_components.intuis_connect.entity.intuis_home import IntuisHome
from custom_components.intuis_connect.intuis_api.api import IntuisAPI, RateLimitError
from custom_components.intuis_connect.utils.const import (
    AUTH_PATH,
    BASE_URLS,
    DOMAIN,
    HOMESDATA_PATH,
)


async def load_registries(hass):
    if hasattr(dr, "async_setup"):
        dr.async_setup(hass)
    await dr.async_load(hass)
    await er.async_load(hass)
    return er.async_get(hass)


def home():
    return IntuisHome.from_api(
        {
            "id": "home",
            "name": "Home",
            "timezone": "UTC",
            "rooms": [
                {"id": "room", "name": "Room", "type": "electricity", "module_ids": []}
            ],
            "schedules": [],
        }
    )


async def test_actual_setup_unload_setup_preserves_registry_entry_and_overrides(
    ha_hass,
    ha_entry_factory,
    monkeypatch,
):
    registry = await load_registries(ha_hass)
    if hasattr(frame, "async_setup"):
        monkeypatch.setattr(frame._hass, "hass", ha_hass)
    entry = ha_entry_factory(
        home_id="home", data={"username": "test@example.com", "home_name": "Home"}
    )
    original_data, original_options = dict(entry.data), dict(entry.options)
    original_identity = (
        entry.entry_id,
        entry.unique_id,
        entry.version,
        entry.minor_version,
    )
    persisted = {
        "room": {
            "mode": "manual",
            "temp": 19.5,
            "end": 9999999999,
            "sticky": True,
            "last_reapply": 0,
        }
    }
    store = Store(ha_hass, 1, f"{DOMAIN}.overrides.{entry.entry_id}")
    await store.async_save({"overrides": persisted})
    api = SimpleNamespace(
        home_id="home",
        home_timezone="UTC",
        circuit_breaker=SimpleNamespace(is_open=False),
        async_refresh_access_token=AsyncMock(),
        async_get_homes_data=AsyncMock(side_effect=lambda: home()),
        async_get_home_status=AsyncMock(
            return_value={
                "modules": [],
                "rooms": [
                    {
                        "id": "room",
                        "therm_setpoint_mode": "manual",
                        "therm_setpoint_temperature": 19.5,
                        "therm_measured_temperature": 20.0,
                        "boost_status": "disabled",
                    }
                ],
            }
        ),
        async_get_config=AsyncMock(return_value={"modules": [{"id": "gateway"}]}),
        async_get_energy_measures=AsyncMock(return_value={}),
        set_rate_limit_callback=lambda cb: None,
    )
    monkeypatch.setattr(
        "custom_components.intuis_connect.IntuisAPI", lambda *a, **kw: api
    )
    monkeypatch.setattr(
        "custom_components.intuis_connect.async_get_clientsession", lambda _: None
    )
    recorded = []

    async def load_platforms(hass_entry, platforms):
        entities = []
        # Actual platform factories calculate the unique IDs; do not reproduce their format.
        await climate.async_setup_entry(
            ha_hass, hass_entry, lambda items, **kw: entities.extend(items)
        )
        await sensor.async_setup_entry(
            ha_hass, hass_entry, lambda items, **kw: entities.extend(items)
        )
        result = {}
        for entity in entities:
            domain = (
                "climate"
                if isinstance(entity, climate.IntuisConnectClimate)
                else "sensor"
            )
            registered = registry.async_get_or_create(
                domain,
                DOMAIN,
                entity.unique_id,
                config_entry=hass_entry,
                suggested_object_id=entity.name,
            )
            result[entity.unique_id] = (
                registered.id,
                registered.entity_id,
                registered.config_entry_id,
            )
        recorded.append(result)

    async def unload_platforms(hass_entry, platforms):
        await ha_hass.data[DOMAIN][hass_entry.entry_id]["coordinator"].async_shutdown()
        return True

    monkeypatch.setattr(
        ha_hass.config_entries, "async_forward_entry_setups", load_platforms
    )
    monkeypatch.setattr(
        ha_hass.config_entries, "async_unload_platforms", unload_platforms
    )
    try:
        for _ in range(2):
            entry._async_set_state(ha_hass, ConfigEntryState.SETUP_IN_PROGRESS, None)
            token = current_entry.set(entry)
            try:
                assert await async_setup_entry(ha_hass, entry)
            finally:
                current_entry.reset(token)
            runtime = ha_hass.data[DOMAIN][entry.entry_id]
            assert runtime["override_manager"].overrides is runtime["overrides"]
            assert runtime["overrides"] == persisted
            assert await store.async_load() == {"overrides": persisted}
            assert await async_unload_entry(ha_hass, entry)
        assert recorded[0] == recorded[1] and recorded[0]
        assert (
            dict(entry.data) == original_data
            and dict(entry.options) == original_options
        )
        assert (
            entry.entry_id,
            entry.unique_id,
            entry.version,
            entry.minor_version,
        ) == original_identity
    finally:
        if entry.entry_id in ha_hass.data.get(DOMAIN, {}):
            await async_unload_entry(ha_hass, entry)


@pytest.mark.parametrize(
    "failure",
    [
        None,
        aiohttp.ClientConnectionError("offline"),
        RateLimitError("429"),
        {"malformed": "home"},
    ],
)
async def test_native_v2_migration_preserves_identity_and_existing_data(
    ha_hass,
    ha_entry_factory,
    monkeypatch,
    failure,
):
    entry = ha_entry_factory(
        home_id="home_abc123",
        data={"username": "test@example.com", "custom_key": "keep"},
    )
    ha_hass.config_entries.async_update_entry(entry, version=2)
    original = deepcopy(dict(entry.data))
    identity = entry.entry_id, entry.unique_id
    response = (
        [{"id": "home_abc123", "name": "My House"}] if failure is None else [failure]
    )
    api = SimpleNamespace(
        async_refresh_access_token=AsyncMock(),
        async_get_all_homes=AsyncMock(return_value=response),
    )
    if isinstance(failure, Exception):
        api.async_refresh_access_token.side_effect = failure
    monkeypatch.setattr(
        "custom_components.intuis_connect.async_get_clientsession", lambda _: None
    )
    monkeypatch.setattr(
        "custom_components.intuis_connect.IntuisAPI", lambda *a, **kw: api
    )
    assert await async_migrate_entry(ha_hass, entry)
    assert entry.version == 3 and (entry.entry_id, entry.unique_id) == identity
    assert all(entry.data[key] == value for key, value in original.items())
    assert entry.data["home_name"] == (
        "My House" if failure is None else "Home home_abc"
    )


async def test_login_returns_actual_homes_over_simulated_http(cloud_responses):
    cloud_responses.post(
        BASE_URLS[0] + AUTH_PATH,
        payload={"access_token": "test-token", "refresh_token": "test-refresh"},
    )
    cloud_responses.get(
        BASE_URLS[0] + HOMESDATA_PATH,
        payload={
            "body": {
                "homes": [
                    {"id": "first", "name": "First", "timezone": "UTC"},
                    {"id": "second", "name": "Second", "timezone": "Europe/Paris"},
                ]
            }
        },
    )
    async with aiohttp.ClientSession() as session:
        api = IntuisAPI(session, min_request_delay=0)
        homes = await api.async_login("test@example.com", "test-only")
    assert [item["id"] for item in homes] == ["first", "second"]
    assert api.refresh_token == "test-refresh"


async def test_get_homes_data_resolves_requested_home_over_simulated_http(
    cloud_responses,
):
    cloud_responses.get(
        BASE_URLS[0] + HOMESDATA_PATH,
        payload={
            "body": {
                "homes": [
                    {"id": "first", "name": "First", "timezone": "UTC", "rooms": []},
                    {
                        "id": "second",
                        "name": "Second",
                        "timezone": "Europe/Paris",
                        "rooms": [],
                    },
                ]
            }
        },
    )
    async with aiohttp.ClientSession() as session:
        api = IntuisAPI(session, home_id="first", min_request_delay=0)
        api._access_token = "test-token"
        result = await api.async_get_homes_data(target_home_id="second")
    assert result.id == api.home_id == "second" and result.name == "Second"
    assert api.home_timezone == "Europe/Paris"


@pytest.mark.parametrize("temp,duration", [(None, 5), (19.5, None)])
async def test_incomplete_timed_command_is_rejected_before_transport(temp, duration):
    from custom_components.intuis_connect.overrides import OverrideManager

    api = SimpleNamespace(async_set_room_state=AsyncMock())
    manager = OverrideManager()
    with pytest.raises(ValueError, match="temperature and duration"):
        await manager.async_command(api, "room", "manual", temp, duration)
    api.async_set_room_state.assert_not_awaited()
    assert manager.overrides == {}
