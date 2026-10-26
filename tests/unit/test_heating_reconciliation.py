"""Heating regressions through real mapping, coordinator callbacks and HA Store."""

from __future__ import annotations

import asyncio
from copy import deepcopy
import logging
import inspect
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.intuis_connect.climate import IntuisConnectClimate
from custom_components.intuis_connect.entity.intuis_room import IntuisRoomDefinition
from custom_components.intuis_connect.intuis_api.api import APIError, CannotConnect
from custom_components.intuis_connect.intuis_data import IntuisData
from custom_components.intuis_connect.overrides import OverrideManager
from custom_components.intuis_connect.utils.const import (
    DOMAIN,
    PRESET_AWAY,
    PRESET_BOOST,
    PRESET_SCHEDULE,
    PRESET_FROST_PROTECT,
)


@pytest.fixture
async def heating(ha_hass, ha_entry_factory):
    options = {
        "manual_duration": 5,
        "boost_duration": 30,
        "away_duration": 60,
        "boost_temp": 25.0,
        "away_temp": 16.0,
        "indefinite_mode": False,
    }
    entry = ha_entry_factory(options=options)
    raw_room = {
        "id": "room",
        "therm_setpoint_mode": "auto",
        "therm_setpoint_temperature": 20.0,
        "therm_measured_temperature": 20.0,
        "boost_status": "disabled",
        "therm_setpoint_end_time": 0,
    }
    api = SimpleNamespace(
        home_timezone="UTC",
        async_set_room_state=AsyncMock(),
        async_get_home_status=AsyncMock(
            side_effect=lambda: {"rooms": [dict(raw_room)], "modules": []}
        ),
        async_get_config=AsyncMock(return_value={"modules": [{"id": "gateway"}]}),
        async_get_energy_measures=AsyncMock(return_value={}),
    )
    home = SimpleNamespace(
        id="home",
        schedules=[],
        rooms={
            "room": IntuisRoomDefinition("room", "Room", "electricity", module_ids=[]),
        },
    )
    shared = {}
    store = Store(ha_hass, 1, f"{DOMAIN}.overrides.{entry.entry_id}")

    async def save():
        await store.async_save({"overrides": deepcopy(shared)})

    manager = OverrideManager(shared, save)
    data = IntuisData(
        api, home, shared, lambda: options, save, override_manager=manager
    )
    coordinator_kwargs = (
        {"config_entry": entry}
        if "config_entry" in inspect.signature(DataUpdateCoordinator).parameters
        else {}
    )
    coordinator = DataUpdateCoordinator(
        ha_hass,
        logging.getLogger(__name__),
        name="heating",
        update_method=data.async_update,
        **coordinator_kwargs,
    )
    await coordinator.async_refresh()
    ha_hass.data[DOMAIN] = {
        entry.entry_id: {
            "overrides": shared,
            "override_manager": manager,
            "coordinator": coordinator,
            "save_overrides": save,
        }
    }
    entity = IntuisConnectClimate(
        coordinator, "home", coordinator.data["rooms"]["room"], api, entry.entry_id
    )
    entity.hass = ha_hass
    entity.entity_id = "climate.room"
    entity.async_write_ha_state = MagicMock()
    # Register the production CoordinatorEntity listener, without setting up any cloud platform.
    await entity.async_added_to_hass()
    yield SimpleNamespace(
        entity=entity,
        data=data,
        manager=manager,
        shared=shared,
        api=api,
        coordinator=coordinator,
        raw=raw_room,
        store=store,
        options=options,
        hass=ha_hass,
        entry=entry,
    )
    await entity.async_remove(force_remove=True)


async def publish(heating):
    await heating.coordinator.async_refresh()


async def test_empty_start_command_visible_to_real_data_and_native_storage(heating):
    h = heating
    assert h.data._overrides is h.shared is h.manager.overrides
    await h.entity.async_set_temperature(temperature=19.5)
    assert h.shared["room"]["temp"] == 19.5
    assert (await h.store.async_load())["overrides"] == h.shared
    h.options["indefinite_mode"] = True
    h.options["manual_duration"] = 7  # Reapplication has a genuinely later end.
    previous_timer = h.entity._cancel_end
    h.shared["room"].update(
        end=int(time.time()) + 30, last_reapply=int(time.time()) - 180
    )
    await publish(h)
    assert h.entity._cancel_end is not previous_timer
    assert h.entity._scheduled_end_ts == h.shared["room"]["end"]
    assert h.api.async_set_room_state.await_count == 2
    assert h.shared["room"]["end"] > int(time.time()) + 30
    assert (await h.store.async_load())["overrides"] == h.shared


async def test_expiration_removes_shared_and_persisted_intent(heating):
    h = heating
    await h.entity.async_set_temperature(temperature=19.5)
    h.shared["room"]["end"] = int(time.time()) - 1
    await publish(h)
    assert h.shared == {} and (await h.store.async_load())["overrides"] == {}


async def test_saved_intentions_are_reused_after_recreation(heating):
    h = heating
    await h.entity.async_set_temperature(temperature=19.5)
    loaded = (await h.store.async_load())["overrides"]
    manager = OverrideManager(loaded, AsyncMock())
    recreated = IntuisData(
        h.api,
        h.data._intuis_home,
        override_manager=manager,
        get_options=lambda: h.options,
    )
    await recreated.async_update()
    assert recreated._overrides is loaded and loaded["room"]["temp"] == 19.5


@pytest.mark.parametrize("command", ["manual", "boost", "off"])
async def test_refused_command_creates_no_intent_or_pending_state(heating, command):
    h = heating
    h.api.async_set_room_state.side_effect = APIError("refused")
    with pytest.raises(APIError):
        if command == "manual":
            await h.entity.async_set_temperature(temperature=19.5)
        elif command == "boost":
            await h.entity.async_set_preset_mode(PRESET_BOOST)
        else:
            await h.entity.async_set_hvac_mode(HVACMode.OFF)
    assert h.shared == {} and h.entity._pending is None
    assert h.entity._cancel_pending is None and h.entity._cancel_end is None
    h.entity.async_write_ha_state.assert_not_called()
    assert await h.store.async_load() is None


@pytest.mark.parametrize(
    "mode,preset,temp", [("manual", None, 19.5), ("boost", PRESET_BOOST, 25.0)]
)
async def test_confirmation_then_external_change_uses_coordinator_callback(
    heating, mode, preset, temp
):
    h = heating
    if mode == "manual":
        await h.entity.async_set_temperature(temperature=temp)
    else:
        await h.entity.async_set_preset_mode(preset)
    assert h.entity._pending is not None
    h.raw.update(
        therm_setpoint_mode=mode,
        therm_setpoint_temperature=temp,
        boost_status="in_progress" if mode == "boost" else "disabled",
    )
    await publish(h)
    assert h.entity._pending is None and not h.entity.assumed_state
    h.raw.update(
        therm_setpoint_mode="auto",
        boost_status="disabled",
        therm_setpoint_temperature=20,
    )
    await publish(h)
    assert (
        h.entity.hvac_mode == HVACMode.AUTO and h.entity.preset_mode == PRESET_SCHEDULE
    )


@pytest.mark.parametrize("preset", [PRESET_BOOST, PRESET_FROST_PROTECT])
async def test_local_optimism_expires_even_if_cloud_refresh_fails(
    heating, monkeypatch, preset
):
    h = heating
    # Long enough that the optimistic window survives the failing refresh below,
    # short enough to expire while the test waits for it.
    monkeypatch.setattr(
        "custom_components.intuis_connect.climate.OPTIMISTIC_TIMEOUT", 0.5
    )
    h.api.async_get_home_status.side_effect = CannotConnect("offline")
    await h.entity.async_set_preset_mode(preset)
    assert h.entity._pending is not None
    assert not h.entity.available  # Preserve CoordinatorEntity availability.
    async with asyncio.timeout(5):
        while h.entity._pending is not None:
            await asyncio.sleep(0.01)
    assert (
        h.entity.hvac_mode == HVACMode.AUTO and h.entity.preset_mode == PRESET_SCHEDULE
    )
    assert not h.entity.assumed_state


async def test_manual_encoded_preset_checks_observed_expiration(heating):
    h = heating
    await h.entity.async_set_preset_mode(PRESET_AWAY)
    end = h.shared["room"]["end"]
    h.raw.update(
        therm_setpoint_mode="manual",
        therm_setpoint_temperature=16,
        therm_setpoint_end_time=end,
    )
    await publish(h)
    assert h.entity.preset_mode == PRESET_AWAY and h.entity._pending is None
    assert h.entity.hvac_mode == HVACMode.AUTO
    # Same temperature, but a distinct external manual override must not inherit Away.
    h.raw["therm_setpoint_end_time"] = end + 3600
    await publish(h)
    assert h.entity.preset_mode is None


async def test_timers_replaced_and_cancelled_on_entity_removal(heating):
    h = heating
    await h.entity.async_set_preset_mode(PRESET_BOOST)
    first_pending, first_end = h.entity._cancel_pending, h.entity._cancel_end
    await h.entity.async_set_temperature(temperature=19.5)
    assert (
        h.entity._cancel_pending is not first_pending
        and h.entity._cancel_end is not first_end
    )
    await h.entity.async_remove(force_remove=True)
    assert h.entity._cancel_pending is None and h.entity._cancel_end is None
    assert h.entity._pending is None
    h.entity.async_write_ha_state.reset_mock()
    await asyncio.sleep(0.01)
    h.entity.async_write_ha_state.assert_not_called()
    assert (
        not h.coordinator._listeners
    )  # Entity listener unsubscribed by its lifecycle.


async def test_late_command_completion_cannot_resurrect_removed_entity(heating):
    h = heating
    entered, release = asyncio.Event(), asyncio.Event()

    async def delayed(*args):
        entered.set()
        await release.wait()

    h.api.async_set_room_state.side_effect = delayed
    task = asyncio.create_task(h.entity.async_set_preset_mode(PRESET_BOOST))
    await entered.wait()
    await h.entity.async_remove(force_remove=True)
    h.entity.async_write_ha_state.reset_mock()
    refresh = AsyncMock()
    h.coordinator.async_request_refresh = refresh
    release.set()
    await task
    assert h.entity._pending is None and h.entity._cancel_end is None
    h.entity.async_write_ha_state.assert_not_called()
    refresh.assert_not_awaited()


async def test_disk_failure_keeps_accepted_command_distinct_from_refusal(
    heating, monkeypatch
):
    h = heating

    async def fail():
        raise OSError("disk full")

    monkeypatch.setattr(h.manager, "_save_callback", fail)
    with pytest.raises(OSError, match="disk full"):
        await h.entity.async_set_temperature(temperature=19.5)
    h.api.async_set_room_state.assert_awaited_once()
    assert h.shared["room"]["temp"] == 19.5 and h.entity._pending is not None
    assert h.entity.hvac_mode == HVACMode.HEAT


async def test_new_user_command_wins_over_an_inflight_sticky_reapply(heating):
    h = heating
    await h.entity.async_set_temperature(temperature=19.5)
    h.options["indefinite_mode"] = True
    h.shared["room"].update(
        end=int(time.time()) + 30, last_reapply=int(time.time()) - 180
    )
    entered, release = asyncio.Event(), asyncio.Event()

    async def delayed(*args):
        if args[2] == 19.5:
            entered.set()
            await release.wait()

    h.api.async_set_room_state.side_effect = delayed
    update = asyncio.create_task(h.data.async_update())
    await entered.wait()
    command = asyncio.create_task(h.entity.async_set_temperature(temperature=22.5))
    await asyncio.sleep(0)
    release.set()
    await update
    await command
    assert h.shared["room"]["temp"] == 22.5
    assert (await h.store.async_load())["overrides"]["room"]["temp"] == 22.5


async def test_expired_snapshot_does_not_remove_a_newer_intent(heating):
    h = heating
    first = h.manager.record("room", "manual", 19.5, 5)
    h.manager.record("room", "manual", 22.5, 5)
    assert not h.manager.discard("room", first)
    assert h.shared["room"]["temp"] == 22.5
