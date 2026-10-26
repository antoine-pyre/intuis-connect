"""Verify the test boundaries before using them to protect integration behavior."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiohttp
import pytest
import voluptuous as vol
from homeassistant.components.recorder.db_schema import Statistics, StatisticsMeta
from homeassistant.helpers.storage import Store
from sqlalchemy import delete, select

from custom_components.intuis_connect.services import async_register_services
from custom_components.intuis_connect.utils.const import DOMAIN


async def test_actual_service_registry_runs_schema_and_handler(
    ha_hass, ha_entry_factory, monkeypatch
):
    """Exercise a production service through HA, including its active schema."""
    entry = ha_entry_factory()
    api = SimpleNamespace(
        async_get_homes_data=AsyncMock(
            return_value=SimpleNamespace(schedules=[], rooms={})
        )
    )
    coordinator = SimpleNamespace(async_request_refresh=AsyncMock())
    ha_hass.data[DOMAIN] = {
        entry.entry_id: {
            "api": api,
            "intuis_home": SimpleNamespace(
                id="home_123", name="Test home", schedules=[], rooms={}
            ),
            "coordinator": coordinator,
        }
    }
    await async_register_services(ha_hass, entry)
    # Invalid field fails in the real schema before any HTTP boundary is touched.
    with pytest.raises(vol.Invalid):
        await ha_hass.services.async_call(
            DOMAIN, "refresh_schedules", {"unexpected": True}, blocking=True
        )
    api.async_get_homes_data.assert_not_awaited()
    # A valid home reaches the production handler.
    await ha_hass.services.async_call(
        DOMAIN, "refresh_schedules", {"home_id": "home_123"}, blocking=True
    )
    api.async_get_homes_data.assert_awaited_once()
    coordinator.async_request_refresh.assert_awaited_once()
    assert ha_hass.config_entries.async_get_entry(entry.entry_id) is entry


async def test_native_store_round_trip(ha_hass):
    store = Store(ha_hass, 1, "intuis_connect.test_overrides")
    payload = {"overrides": {"room": {"mode": "manual", "temp": 19.5}}}
    await asyncio.wait_for(store.async_save(payload), timeout=3)
    assert (
        await asyncio.wait_for(
            Store(ha_hass, 1, "intuis_connect.test_overrides").async_load(), timeout=3
        )
        == payload
    )


def test_recorder_sqlite_transaction_rolls_back(recorder_session_factory):
    """An actual HA statistics row survives a failed destructive transaction."""
    with recorder_session_factory.begin() as session:
        meta = StatisticsMeta(
            statistic_id="sensor.test_energy", source="recorder", has_sum=True
        )
        session.add(meta)
        session.flush()
        metadata_id = meta.id
        session.add(Statistics(metadata_id=metadata_id, start_ts=0, state=1.0, sum=1.0))
    with pytest.raises(RuntimeError, match="write failed"):
        with recorder_session_factory.begin() as session:
            session.execute(
                delete(Statistics).where(Statistics.metadata_id == metadata_id)
            )
            raise RuntimeError("write failed")
    with recorder_session_factory() as session:
        row = session.execute(select(Statistics)).scalar_one()
        assert row.sum == 1.0


async def test_real_aiohttp_transport_fixture(cloud_responses):
    cloud_responses.get("https://intuis.invalid/test", payload={"body": "simulated"})
    async with aiohttp.ClientSession() as session:
        async with session.get("https://intuis.invalid/test") as response:
            assert await response.json() == {"body": "simulated"}
        with pytest.raises(aiohttp.ClientConnectionError):
            await session.get("https://intuis.invalid/unexpected")
