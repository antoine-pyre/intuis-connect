"""Temperature values stay native when a newer Core converts display units."""

from __future__ import annotations

import importlib.util
import inspect
import logging
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components import climate as climate_platform
from homeassistant.components.climate import HVACMode
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.intuis_connect import climate
from custom_components.intuis_connect.utils.const import DOMAIN


@pytest.mark.parametrize("native_core", [False, True])
async def test_temperature_api_keeps_commands_in_device_units(
    ha_hass, ha_entry_factory, monkeypatch, native_core
):
    """Simulate conversion hooks; this is not a full newer-Core validation."""
    if native_core:
        class ConvertingClimateEntity(climate_platform.ClimateEntity):
            native_current_temperature = None
            native_target_temperature = None

            @property
            def current_temperature(self):
                return self.native_current_temperature + 273.15

            @property
            def target_temperature(self):
                return self.native_target_temperature + 273.15

        monkeypatch.setattr(climate_platform, "ClimateEntity", ConvertingClimateEntity)

    name = "custom_components.intuis_connect._temperature_api_test"
    spec = importlib.util.spec_from_file_location(name, climate.__file__)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    assert module._NATIVE_TEMPERATURES is native_core
    if native_core:
        assert "current_temperature" not in module.IntuisConnectClimate.__dict__
        assert "target_temperature" not in module.IntuisConnectClimate.__dict__

    entry = ha_entry_factory(options={"manual_duration": 5})
    kwargs = {"config_entry": entry} if "config_entry" in inspect.signature(DataUpdateCoordinator).parameters else {}
    coordinator = DataUpdateCoordinator(ha_hass, logging.getLogger(__name__), name="temperature", **kwargs)
    room = SimpleNamespace(id="room", name="Room", mode="home", temperature=19.0,
                           target_temperature=20.0, boost_status="disabled",
                           therm_setpoint_end_time=0)
    coordinator.async_set_updated_data({"rooms": {"room": room}})
    coordinator.async_request_refresh = AsyncMock()
    api = SimpleNamespace(async_set_room_state=AsyncMock())
    ha_hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"overrides": {}}
    entity = module.IntuisConnectClimate(coordinator, "home", room, api, entry.entry_id)
    entity.hass = ha_hass
    entity.async_write_ha_state = MagicMock()
    try:
        assert entity.native_current_temperature == 19.0
        assert entity.native_target_temperature == 20.0
        assert entity.target_temperature == (293.15 if native_core else 20.0)
        await entity.async_set_hvac_mode(HVACMode.HEAT)
        api.async_set_room_state.assert_awaited_once_with("room", "manual", 20.0, 5)
        assert entity.native_target_temperature == 20.0
    finally:
        await entity.async_will_remove_from_hass()
