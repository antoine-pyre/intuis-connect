"""Pilot-wire orders through the current intent manager, HA storage and transport.

Behaviour adapted from apeyrat #27 and adrienvsj commits 6eb642b735/04b79ef755.
No account or physical radiator is used.
"""
from __future__ import annotations

import inspect
import json
import logging
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest
from aioresponses import CallbackResult
from homeassistant.components.climate import ClimateEntityFeature, HVACMode
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.intuis_connect import climate as climate_module
from custom_components.intuis_connect.climate import (
    IntuisConnectClimate, IntuisPilotWireClimate, async_setup_entry,
)
from custom_components.intuis_connect.entity.intuis_room import (
    IntuisRoom, IntuisRoomDefinition, is_pilot_wire,
)
from custom_components.intuis_connect.intuis_api.api import APIError, IntuisAPI
from custom_components.intuis_connect.intuis_api.mapper import extract_rooms
from custom_components.intuis_connect.overrides import OverrideManager
from custom_components.intuis_connect.utils.const import BASE_URLS, DOMAIN, PRESET_SCHEDULE


def room(**updates):
    raw = {"id": "wire", "muller_type": "FP4", "therm_setpoint_mode": "home",
           "therm_setpoint_fp": "comfort"}
    raw.update(updates)
    definition = IntuisRoomDefinition("wire", "Wire", "electricity")
    return IntuisRoom.from_dict(definition, raw, [])


@pytest.fixture
async def wire(ha_hass, ha_entry_factory):
    entry = ha_entry_factory(options={"manual_duration": 5})
    store = Store(ha_hass, 1, f"{DOMAIN}.wire.{entry.entry_id}")
    shared = {}

    async def save():
        await store.async_save({"overrides": shared})

    manager = OverrideManager(shared, save)
    kwargs = {"config_entry": entry} if "config_entry" in inspect.signature(DataUpdateCoordinator).parameters else {}
    coordinator = DataUpdateCoordinator(ha_hass, logging.getLogger(__name__), name="wire", **kwargs)
    coordinator.async_set_updated_data({"rooms": {"wire": room()}})
    coordinator.async_request_refresh = AsyncMock()
    api = SimpleNamespace(async_set_room_state=AsyncMock())
    ha_hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "override_manager": manager, "overrides": shared,
    }
    entity = IntuisPilotWireClimate(coordinator, "home", room(), api, entry.entry_id)
    entity.hass = ha_hass
    entity.entity_id = "climate.wire"
    entity.async_write_ha_state = MagicMock()
    yield SimpleNamespace(entity=entity, manager=manager, store=store, shared=shared,
                          coordinator=coordinator, api=api, hass=ha_hass, entry=entry)
    await entity.async_will_remove_from_hass()


@pytest.mark.parametrize("temperature,target,order,expected", [
    (None, None, "comfort", True), (None, None, "away", True),
    (0, None, "comfort", False), (20, 21, "comfort", False),
    (None, 20, "comfort", False), (None, None, None, False),
])
def test_detection_preserves_thermostats_and_requires_order(temperature, target, order, expected):
    mapped = room(therm_measured_temperature=temperature,
                  therm_setpoint_temperature=target, therm_setpoint_fp=order)
    assert is_pilot_wire(mapped) is expected
    assert mapped.temperature == temperature
    assert mapped.target_temperature == target


def test_unknown_or_malformed_rooms_do_not_fail_other_rooms():
    definition = IntuisRoomDefinition("wire", "Wire", "electricity")
    mapped = extract_rooms({"rooms": [None, {}, {"id": "new"},
                                     {"id": "wire", "therm_setpoint_temperature": None}]},
                           [], {}, {"wire": definition}, None)
    assert set(mapped) == {"wire"}
    assert mapped["wire"].temperature is None
    assert mapped["wire"].target_temperature is None
    assert not mapped["wire"].heating


@pytest.mark.parametrize("preset,order", [("comfort", "comfort"), ("eco", "away"),
                                         ("frost_protect", "frost_guard")])
async def test_order_persists_and_reapplies_without_temperature(wire, preset, order):
    w = wire
    await w.entity.async_set_preset_mode(preset)
    w.api.async_set_room_state.assert_awaited_once_with("wire", "manual", None, 5, fp=order)
    assert w.entity.preset_mode == preset
    assert w.entity.target_temperature is None and w.entity.current_temperature is None
    assert not w.entity.supported_features & ClimateEntityFeature.TARGET_TEMPERATURE
    saved = (await w.store.async_load())["overrides"]
    assert saved["wire"]["fp"] == order and saved["wire"]["temp"] is None
    # Reload the saved intent into a fresh manager, as integration startup does.
    restored = OverrideManager(saved)
    assert await restored.async_reapply(w.api, "wire", saved["wire"], 7)
    w.api.async_set_room_state.assert_awaited_with("wire", "manual", None, 7, fp=order)


async def test_order_ack_requires_the_matching_wire_order(wire):
    w = wire
    await w.entity.async_set_preset_mode("eco")
    end = w.shared["wire"]["end"]
    w.coordinator.async_set_updated_data({"rooms": {"wire": room(
        therm_setpoint_mode="manual", therm_setpoint_fp="comfort", therm_setpoint_end_time=end)}})
    w.entity._handle_coordinator_update()
    assert w.entity._pending is not None
    w.coordinator.async_set_updated_data({"rooms": {"wire": room(
        therm_setpoint_mode="manual", therm_setpoint_fp="away", therm_setpoint_end_time=end)}})
    w.entity._handle_coordinator_update()
    assert w.entity._pending is None
    assert w.entity.preset_mode == "eco"
    assert w.entity.hvac_action is None


async def test_refused_order_is_not_persisted_or_published(wire):
    wire.api.async_set_room_state.side_effect = APIError("refused")
    with pytest.raises(APIError):
        await wire.entity.async_set_preset_mode("eco")
    assert wire.shared == {} and wire.entity._pending is None
    assert await wire.store.async_load() is None


@pytest.mark.parametrize("target", [HVACMode.AUTO, HVACMode.OFF])
async def test_schedule_and_off_clear_wire_intention(wire, target):
    await wire.entity.async_set_preset_mode("eco")
    await wire.entity.async_set_hvac_mode(target)
    assert wire.shared == {}
    wire.api.async_set_room_state.assert_awaited_with("wire", "home" if target == HVACMode.AUTO else "off")
    assert wire.entity.hvac_mode == target
    if target == HVACMode.AUTO:
        assert wire.entity.preset_mode == PRESET_SCHEDULE


async def test_wire_rejects_temperature_and_unknown_preset(wire):
    with pytest.raises(ValueError):
        await wire.entity.async_set_temperature(temperature=20)
    with pytest.raises(ValueError):
        await wire.entity.async_set_preset_mode("boost")
    wire.api.async_set_room_state.assert_not_called()


async def test_setup_chooses_wire_class_without_changing_identity(wire, monkeypatch):
    wire_room = room()
    thermal_room = room(therm_measured_temperature=20, therm_setpoint_temperature=21)
    thermal_room.id = "thermostat"
    wire.coordinator.async_set_updated_data({"rooms": {"wire": wire_room, "thermostat": thermal_room}})
    monkeypatch.setattr("custom_components.intuis_connect.climate.get_basic_utils", lambda *_: (
        wire.coordinator, "home", {"wire": wire_room, "thermostat": thermal_room}, wire.api))
    add = MagicMock()
    await async_setup_entry(wire.hass, wire.entry, add)
    entities = add.call_args.args[0]
    assert type(entities[0]) is IntuisPilotWireClimate
    assert type(entities[1]) is IntuisConnectClimate
    assert entities[0].unique_id == "intuis_home_wire_climate"
    # The name, which the entity_id is built from, still comes from _attr_name.
    assert entities[0].translation_key == "pilot_wire"
    assert entities[0].name == "Wire Climate"
    assert entities[1].translation_key is None


def test_every_wire_preset_has_an_icon_and_labels(wire):
    component = Path(climate_module.__file__).parent
    icons = json.loads((component / "icons.json").read_text())
    preset_icons = icons["entity"]["climate"]["pilot_wire"]["state_attributes"]["preset_mode"]
    presets = set(wire.entity.preset_modes)
    assert set(preset_icons["state"]) == presets
    assert preset_icons["state"]["frost_protect"] == "mdi:snowflake"
    for language in ("en", "fr"):
        strings = json.loads((component / "translations" / f"{language}.json").read_text())
        labels = strings["entity"]["climate"]["pilot_wire"]["state_attributes"]["preset_mode"]["state"]
        assert set(labels) == presets


@pytest.mark.parametrize("order", ["comfort", "away", "frost_guard"])
async def test_transport_sends_order_without_temperature(cloud_responses, order):
    seen = []

    def endpoint(url, **kwargs):
        seen.append(kwargs["json"])
        return CallbackResult(payload={"status": "ok"})

    cloud_responses.post(BASE_URLS[0] + "/syncapi/v1/setstate", callback=endpoint)
    async with aiohttp.ClientSession() as session:
        api = IntuisAPI(session, home_id="home", min_request_delay=0)
        api._base_url = BASE_URLS[0]
        api._access_token = "test"
        await api.async_set_room_state("wire", "manual", duration=5, fp=order)
    payload = seen[0]["home"]["rooms"][0]
    assert payload["therm_setpoint_fp"] == order
    assert "therm_setpoint_temperature" not in payload
    assert payload["therm_setpoint_end_time"] >= int(time.time()) + 290


@pytest.mark.parametrize("mode,temp,order", [("manual", 20, "away"),
                                          ("manual", None, "invalid"),
                                          ("home", None, "comfort")])
async def test_invalid_wire_command_never_reaches_transport(mode, temp, order):
    async with aiohttp.ClientSession() as session:
        api = IntuisAPI(session)
        with pytest.raises(APIError):
            await api.async_set_room_state("wire", mode, temp, fp=order)


async def test_missing_temperature_sensor_is_unknown_not_zero(wire):
    from custom_components.intuis_connect.sensor import IntuisTemperatureSensor

    sensor = IntuisTemperatureSensor(wire.coordinator, "home", room())
    assert sensor.native_value is None
    assert wire.entity.native_current_temperature is None
    assert wire.entity.native_target_temperature is None
