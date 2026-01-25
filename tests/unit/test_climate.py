"""Tests for the IntuisConnectClimate entity."""
from __future__ import annotations

import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.components.climate import HVACAction, HVACMode

from custom_components.intuis_connect.utils.const import (
    API_MODE_OFF,
    API_MODE_AUTO,
    API_MODE_MANUAL,
    API_MODE_AWAY,
    API_MODE_BOOST,
    API_MODE_HOME,
    PRESET_AWAY,
    PRESET_BOOST,
    PRESET_SCHEDULE,
    DOMAIN,
)


# ---------------------------------------------------------------------------
# Test: Climate Properties
# ---------------------------------------------------------------------------

class TestClimateProperties:
    """Tests for climate entity properties."""

    def test_current_temperature(self, climate_entity_factory, sample_room):
        """current_temperature returns room temperature."""
        sample_room.temperature = 21.5
        entity = climate_entity_factory(room=sample_room)
        assert entity.current_temperature == 21.5

    def test_target_temperature(self, climate_entity_factory, sample_room):
        """target_temperature returns room target_temperature."""
        sample_room.target_temperature = 22.0
        entity = climate_entity_factory(room=sample_room)
        assert entity.target_temperature == 22.0

    def test_hvac_mode_off(self, climate_entity_factory, sample_room):
        """hvac_mode returns OFF for API_MODE_OFF."""
        sample_room.mode = API_MODE_OFF
        entity = climate_entity_factory(room=sample_room)
        assert entity.hvac_mode == HVACMode.OFF

    def test_hvac_mode_auto(self, climate_entity_factory, sample_room):
        """hvac_mode returns AUTO for API_MODE_AUTO."""
        sample_room.mode = API_MODE_AUTO
        entity = climate_entity_factory(room=sample_room)
        assert entity.hvac_mode == HVACMode.AUTO

    def test_hvac_mode_heat_manual(self, climate_entity_factory, sample_room):
        """hvac_mode returns HEAT for API_MODE_MANUAL."""
        sample_room.mode = API_MODE_MANUAL
        entity = climate_entity_factory(room=sample_room)
        assert entity.hvac_mode == HVACMode.HEAT

    def test_hvac_mode_heat_away(self, climate_entity_factory, sample_room):
        """hvac_mode returns HEAT for API_MODE_AWAY."""
        sample_room.mode = API_MODE_AWAY
        entity = climate_entity_factory(room=sample_room)
        assert entity.hvac_mode == HVACMode.AUTO

    def test_hvac_mode_heat_boost(self, climate_entity_factory, sample_room):
        """hvac_mode returns HEAT for API_MODE_BOOST."""
        sample_room.mode = API_MODE_BOOST
        entity = climate_entity_factory(room=sample_room)
        assert entity.hvac_mode == HVACMode.HEAT

    def test_hvac_mode_heat_home(self, climate_entity_factory, sample_room):
        """hvac_mode returns HEAT for API_MODE_HOME."""
        sample_room.mode = API_MODE_HOME
        entity = climate_entity_factory(room=sample_room)
        assert entity.hvac_mode == HVACMode.AUTO

    def test_hvac_mode_respects_override(self, climate_entity_factory, sample_room):
        """hvac_mode returns override when _attr_hvac_mode is set."""
        sample_room.mode = API_MODE_AUTO
        entity = climate_entity_factory(room=sample_room)
        entity._attr_hvac_mode = HVACMode.OFF
        assert entity.hvac_mode == HVACMode.OFF

    def test_preset_mode_away(self, climate_entity_factory, sample_room):
        """preset_mode returns PRESET_AWAY for API_MODE_AWAY."""
        sample_room.mode = API_MODE_AWAY
        entity = climate_entity_factory(room=sample_room)
        assert entity.preset_mode == PRESET_AWAY

    def test_preset_mode_boost(self, climate_entity_factory, sample_room):
        """preset_mode returns PRESET_BOOST for API_MODE_BOOST."""
        sample_room.mode = API_MODE_BOOST
        entity = climate_entity_factory(room=sample_room)
        assert entity.preset_mode == PRESET_BOOST

    def test_preset_mode_schedule_in_auto(self, climate_entity_factory, sample_room):
        """preset_mode returns PRESET_SCHEDULE when in AUTO mode."""
        sample_room.mode = API_MODE_AUTO
        entity = climate_entity_factory(room=sample_room)
        assert entity.preset_mode == PRESET_SCHEDULE

    def test_preset_mode_none_in_manual(self, climate_entity_factory, sample_room):
        """preset_mode returns None when in MANUAL mode."""
        sample_room.mode = API_MODE_MANUAL
        entity = climate_entity_factory(room=sample_room)
        assert entity.preset_mode is None

    def test_hvac_action_off(self, climate_entity_factory, sample_room):
        """hvac_action returns OFF when hvac_mode is OFF."""
        sample_room.mode = API_MODE_OFF
        sample_room.heating = False
        entity = climate_entity_factory(room=sample_room)
        assert entity.hvac_action == HVACAction.OFF

    def test_hvac_action_heating(self, climate_entity_factory, sample_room):
        """hvac_action returns HEATING when room is heating."""
        sample_room.mode = API_MODE_MANUAL
        sample_room.heating = True
        entity = climate_entity_factory(room=sample_room)
        assert entity.hvac_action == HVACAction.HEATING

    def test_hvac_action_idle(self, climate_entity_factory, sample_room):
        """hvac_action returns IDLE when not heating."""
        sample_room.mode = API_MODE_MANUAL
        sample_room.heating = False
        entity = climate_entity_factory(room=sample_room)
        assert entity.hvac_action == HVACAction.IDLE


# ---------------------------------------------------------------------------
# Test: async_set_temperature
# ---------------------------------------------------------------------------

class TestAsyncSetTemperature:
    """Tests for setting temperature."""

    @pytest.mark.asyncio
    async def test_set_temperature_calls_api(
        self, climate_entity_factory, mock_api, sample_room, default_options
    ):
        """Setting temperature calls API with correct parameters."""
        entity = climate_entity_factory(options=default_options)

        await entity.async_set_temperature(temperature=23.5)

        mock_api.async_set_room_state.assert_called_once_with(
            "room_123",
            API_MODE_MANUAL,
            23.5,
            5,  # manual_duration from default_options
        )

    @pytest.mark.asyncio
    async def test_set_temperature_none_returns_early(
        self, climate_entity_factory, mock_api
    ):
        """Setting temperature with None returns early without API call."""
        entity = climate_entity_factory()

        await entity.async_set_temperature(temperature=None)

        mock_api.async_set_room_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_set_temperature_stores_override(
        self, climate_entity_factory, mock_hass, default_options
    ):
        """Setting temperature stores override in hass.data."""
        overrides = {}
        entity = climate_entity_factory(options=default_options, overrides=overrides)

        await entity.async_set_temperature(temperature=23.5)

        assert "room_123" in overrides
        assert overrides["room_123"]["mode"] == API_MODE_MANUAL
        assert overrides["room_123"]["temp"] == 23.5
        assert overrides["room_123"]["sticky"] is True
        assert "end" in overrides["room_123"]
        assert "last_reapply" in overrides["room_123"]

    @pytest.mark.asyncio
    async def test_set_temperature_calls_save_overrides(
        self, climate_entity_factory, mock_save_overrides
    ):
        """Setting temperature persists overrides to storage."""
        entity = climate_entity_factory()

        await entity.async_set_temperature(temperature=23.5)

        mock_save_overrides.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_temperature_updates_state(
        self, climate_entity_factory
    ):
        """Setting temperature updates entity state attributes."""
        entity = climate_entity_factory()

        await entity.async_set_temperature(temperature=23.5)

        assert entity._attr_target_temperature == 23.5
        assert entity._attr_hvac_mode == HVACMode.HEAT
        assert entity._attr_preset_mode is None
        entity.async_write_ha_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_temperature_requests_refresh(
        self, climate_entity_factory, mock_coordinator
    ):
        """Setting temperature requests coordinator refresh."""
        entity = climate_entity_factory()

        await entity.async_set_temperature(temperature=23.5)

        mock_coordinator.async_request_refresh.assert_called_once()


# ---------------------------------------------------------------------------
# Test: async_set_hvac_mode
# ---------------------------------------------------------------------------

class TestAsyncSetHVACMode:
    """Tests for setting HVAC mode."""

    @pytest.mark.asyncio
    async def test_set_hvac_mode_off(
        self, climate_entity_factory, mock_api, sample_room
    ):
        """Setting HVAC mode OFF calls API correctly."""
        entity = climate_entity_factory()

        await entity.async_set_hvac_mode(HVACMode.OFF)

        mock_api.async_set_room_state.assert_called_once_with(
            "room_123", API_MODE_OFF
        )

    @pytest.mark.asyncio
    async def test_set_hvac_mode_off_clears_override(
        self, climate_entity_factory
    ):
        """Setting HVAC mode OFF clears existing override."""
        overrides = {"room_123": {"mode": API_MODE_MANUAL, "temp": 23.0}}
        entity = climate_entity_factory(overrides=overrides)

        await entity.async_set_hvac_mode(HVACMode.OFF)

        assert "room_123" not in overrides

    @pytest.mark.asyncio
    async def test_set_hvac_mode_auto(
        self, climate_entity_factory, mock_api
    ):
        """Setting HVAC mode AUTO calls API with HOME mode."""
        entity = climate_entity_factory()

        await entity.async_set_hvac_mode(HVACMode.AUTO)

        mock_api.async_set_room_state.assert_called_once_with(
            "room_123", API_MODE_HOME
        )

    @pytest.mark.asyncio
    async def test_set_hvac_mode_auto_clears_override(
        self, climate_entity_factory
    ):
        """Setting HVAC mode AUTO clears existing override."""
        overrides = {"room_123": {"mode": API_MODE_MANUAL, "temp": 23.0}}
        entity = climate_entity_factory(overrides=overrides)

        await entity.async_set_hvac_mode(HVACMode.AUTO)

        assert "room_123" not in overrides

    @pytest.mark.asyncio
    async def test_set_hvac_mode_auto_sets_schedule_preset(
        self, climate_entity_factory
    ):
        """Setting HVAC mode AUTO sets preset to SCHEDULE."""
        entity = climate_entity_factory()

        await entity.async_set_hvac_mode(HVACMode.AUTO)

        assert entity._attr_preset_mode == PRESET_SCHEDULE

    @pytest.mark.asyncio
    async def test_set_hvac_mode_heat(
        self, climate_entity_factory, mock_api, sample_room, default_options
    ):
        """Setting HVAC mode HEAT calls API with MANUAL mode."""
        sample_room.target_temperature = 22.0
        entity = climate_entity_factory(options=default_options)

        await entity.async_set_hvac_mode(HVACMode.HEAT)

        mock_api.async_set_room_state.assert_called_once_with(
            "room_123", API_MODE_MANUAL, 22.0, 5
        )

    @pytest.mark.asyncio
    async def test_set_hvac_mode_heat_default_temp(
        self, climate_entity_factory, mock_api, sample_room, default_options
    ):
        """Setting HVAC mode HEAT uses default 20.0 if no target_temperature."""
        sample_room.target_temperature = None
        entity = climate_entity_factory(options=default_options)

        await entity.async_set_hvac_mode(HVACMode.HEAT)

        mock_api.async_set_room_state.assert_called_once_with(
            "room_123", API_MODE_MANUAL, 20.0, 5
        )

    @pytest.mark.asyncio
    async def test_set_hvac_mode_heat_creates_override(
        self, climate_entity_factory, sample_room
    ):
        """Setting HVAC mode HEAT creates override."""
        sample_room.target_temperature = 22.0
        overrides = {}
        entity = climate_entity_factory(overrides=overrides)

        await entity.async_set_hvac_mode(HVACMode.HEAT)

        assert "room_123" in overrides
        assert overrides["room_123"]["mode"] == API_MODE_MANUAL
        assert overrides["room_123"]["temp"] == 22.0

    @pytest.mark.asyncio
    async def test_set_hvac_mode_saves_when_changed(
        self, climate_entity_factory, mock_save_overrides
    ):
        """Setting HVAC mode saves overrides when changed."""
        overrides = {"room_123": {"mode": API_MODE_MANUAL, "temp": 23.0}}
        entity = climate_entity_factory(overrides=overrides)

        await entity.async_set_hvac_mode(HVACMode.OFF)

        mock_save_overrides.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_hvac_mode_no_save_when_unchanged(
        self, climate_entity_factory, mock_save_overrides
    ):
        """Setting HVAC mode doesn't save if no override existed."""
        entity = climate_entity_factory(overrides={})

        await entity.async_set_hvac_mode(HVACMode.OFF)

        mock_save_overrides.assert_not_called()

    @pytest.mark.asyncio
    async def test_set_hvac_mode_off_updates_hvac_mode_attr(
        self, climate_entity_factory
    ):
        """Setting HVAC mode OFF updates _attr_hvac_mode."""
        entity = climate_entity_factory()

        await entity.async_set_hvac_mode(HVACMode.OFF)

        assert entity._attr_hvac_mode == HVACMode.OFF

    @pytest.mark.asyncio
    async def test_set_hvac_mode_auto_updates_hvac_mode_attr(
        self, climate_entity_factory
    ):
        """Setting HVAC mode AUTO updates _attr_hvac_mode."""
        entity = climate_entity_factory()

        await entity.async_set_hvac_mode(HVACMode.AUTO)

        assert entity._attr_hvac_mode == HVACMode.AUTO

    @pytest.mark.asyncio
    async def test_set_hvac_mode_heat_updates_hvac_mode_attr(
        self, climate_entity_factory
    ):
        """Setting HVAC mode HEAT updates _attr_hvac_mode."""
        entity = climate_entity_factory()

        await entity.async_set_hvac_mode(HVACMode.HEAT)

        assert entity._attr_hvac_mode == HVACMode.HEAT


# ---------------------------------------------------------------------------
# Test: async_set_preset_mode
# ---------------------------------------------------------------------------

class TestAsyncSetPresetMode:
    """Tests for setting preset mode."""

    @pytest.mark.asyncio
    async def test_set_preset_schedule(
        self, climate_entity_factory, mock_api
    ):
        """Setting preset SCHEDULE calls API with HOME mode."""
        entity = climate_entity_factory()

        await entity.async_set_preset_mode(PRESET_SCHEDULE)

        mock_api.async_set_room_state.assert_called_once_with(
            "room_123", API_MODE_HOME
        )

    @pytest.mark.asyncio
    async def test_set_preset_schedule_clears_override(
        self, climate_entity_factory
    ):
        """Setting preset SCHEDULE clears existing override."""
        overrides = {"room_123": {"mode": API_MODE_BOOST, "temp": 30.0}}
        entity = climate_entity_factory(overrides=overrides)

        await entity.async_set_preset_mode(PRESET_SCHEDULE)

        assert "room_123" not in overrides

    @pytest.mark.asyncio
    async def test_set_preset_schedule_sets_auto_mode(
        self, climate_entity_factory
    ):
        """Setting preset SCHEDULE sets hvac_mode to AUTO."""
        entity = climate_entity_factory()

        await entity.async_set_preset_mode(PRESET_SCHEDULE)

        assert entity._attr_hvac_mode == HVACMode.AUTO

    @pytest.mark.asyncio
    async def test_set_preset_away(
        self, climate_entity_factory, mock_api, default_options
    ):
        """Setting preset AWAY calls API with correct parameters."""
        entity = climate_entity_factory(options=default_options)

        await entity.async_set_preset_mode(PRESET_AWAY)

        mock_api.async_set_room_state.assert_called_once_with(
            "room_123", API_MODE_AWAY, 16.0, 1440
        )

    @pytest.mark.asyncio
    async def test_set_preset_away_creates_override(
        self, climate_entity_factory, default_options
    ):
        """Setting preset AWAY creates override."""
        overrides = {}
        entity = climate_entity_factory(options=default_options, overrides=overrides)

        await entity.async_set_preset_mode(PRESET_AWAY)

        assert "room_123" in overrides
        assert overrides["room_123"]["mode"] == API_MODE_AWAY
        assert overrides["room_123"]["temp"] == 16.0

    @pytest.mark.asyncio
    async def test_set_preset_away_sets_heat_mode(
        self, climate_entity_factory
    ):
        """Setting preset AWAY sets hvac_mode to HEAT."""
        entity = climate_entity_factory()

        await entity.async_set_preset_mode(PRESET_AWAY)

        assert entity._attr_hvac_mode == HVACMode.AUTO

    @pytest.mark.asyncio
    async def test_set_preset_boost(
        self, climate_entity_factory, mock_api, default_options
    ):
        """Setting preset BOOST calls API with correct parameters."""
        entity = climate_entity_factory(options=default_options)

        await entity.async_set_preset_mode(PRESET_BOOST)

        mock_api.async_set_room_state.assert_called_once_with(
            "room_123", API_MODE_BOOST, 30.0, 30
        )

    @pytest.mark.asyncio
    async def test_set_preset_boost_creates_override(
        self, climate_entity_factory, default_options
    ):
        """Setting preset BOOST creates override."""
        overrides = {}
        entity = climate_entity_factory(options=default_options, overrides=overrides)

        await entity.async_set_preset_mode(PRESET_BOOST)

        assert "room_123" in overrides
        assert overrides["room_123"]["mode"] == API_MODE_BOOST
        assert overrides["room_123"]["temp"] == 30.0

    @pytest.mark.asyncio
    async def test_set_preset_boost_sets_heat_mode(
        self, climate_entity_factory
    ):
        """Setting preset BOOST sets hvac_mode to HEAT."""
        entity = climate_entity_factory()

        await entity.async_set_preset_mode(PRESET_BOOST)

        assert entity._attr_hvac_mode == HVACMode.HEAT

    @pytest.mark.asyncio
    async def test_set_preset_updates_preset_attr(
        self, climate_entity_factory
    ):
        """Setting preset mode updates _attr_preset_mode."""
        entity = climate_entity_factory()

        await entity.async_set_preset_mode(PRESET_BOOST)

        assert entity._attr_preset_mode == PRESET_BOOST


# ---------------------------------------------------------------------------
# Test: Helper Methods
# ---------------------------------------------------------------------------

class TestClimateHelperMethods:
    """Tests for climate helper methods."""

    def test_get_overrides_returns_dict(
        self, climate_entity_factory
    ):
        """_get_overrides returns overrides dict from hass.data."""
        overrides = {"room_123": {"mode": API_MODE_MANUAL}}
        entity = climate_entity_factory(overrides=overrides)

        result = entity._get_overrides()

        assert result == overrides

    def test_get_overrides_returns_empty_when_missing(
        self, climate_entity_factory, mock_hass
    ):
        """_get_overrides returns empty dict when data missing."""
        entity = climate_entity_factory()
        mock_hass.data = {}  # Clear data

        result = entity._get_overrides()

        assert result == {}

    def test_get_save_overrides_returns_callback(
        self, climate_entity_factory, mock_save_overrides
    ):
        """_get_save_overrides returns the callback."""
        entity = climate_entity_factory()

        result = entity._get_save_overrides()

        assert result == mock_save_overrides

    def test_get_option_returns_value(
        self, climate_entity_factory, default_options
    ):
        """_get_option returns value from config entry options."""
        entity = climate_entity_factory(options=default_options)

        result = entity._get_option("manual_duration", 10)

        assert result == 5  # From default_options

    def test_get_option_returns_default(
        self, climate_entity_factory, default_options
    ):
        """_get_option returns default when key missing."""
        entity = climate_entity_factory(options=default_options)

        result = entity._get_option("nonexistent_key", 42)

        assert result == 42


# ---------------------------------------------------------------------------
# Test: Edge Cases
# ---------------------------------------------------------------------------

class TestClimateEdgeCases:
    """Tests for edge cases in climate entity."""

    @pytest.mark.asyncio
    async def test_set_temperature_with_custom_duration(
        self, climate_entity_factory, mock_api
    ):
        """Setting temperature uses custom manual_duration from options."""
        custom_options = {"manual_duration": 60}  # 60 minutes
        entity = climate_entity_factory(options=custom_options)

        await entity.async_set_temperature(temperature=25.0)

        mock_api.async_set_room_state.assert_called_once_with(
            "room_123", API_MODE_MANUAL, 25.0, 60
        )

    @pytest.mark.asyncio
    async def test_override_end_timestamp_calculation(
        self, climate_entity_factory
    ):
        """Override end timestamp is correctly calculated."""
        options = {"manual_duration": 10}  # 10 minutes
        overrides = {}
        entity = climate_entity_factory(options=options, overrides=overrides)

        before = int(time.time())
        await entity.async_set_temperature(temperature=23.0)
        after = int(time.time())

        end_ts = overrides["room_123"]["end"]
        expected_min = before + 10 * 60
        expected_max = after + 10 * 60

        assert expected_min <= end_ts <= expected_max

    @pytest.mark.asyncio
    async def test_last_reapply_timestamp_set(
        self, climate_entity_factory
    ):
        """last_reapply is set to current time when creating override."""
        overrides = {}
        entity = climate_entity_factory(overrides=overrides)

        before = int(time.time())
        await entity.async_set_temperature(temperature=23.0)
        after = int(time.time())

        last_reapply = overrides["room_123"]["last_reapply"]
        assert before <= last_reapply <= after

    def test_unknown_hvac_mode_returns_heat(
        self, climate_entity_factory, sample_room
    ):
        """Unknown HVAC mode defaults to HEAT with warning."""
        sample_room.mode = "unknown_mode"
        entity = climate_entity_factory(room=sample_room)

        result = entity.hvac_mode

        assert result == HVACMode.HEAT

    @pytest.mark.asyncio
    async def test_transition_off_to_heat(
        self, climate_entity_factory, mock_api, sample_room
    ):
        """Transitioning from OFF to HEAT works correctly."""
        sample_room.mode = API_MODE_OFF
        sample_room.target_temperature = 20.0
        entity = climate_entity_factory()

        await entity.async_set_hvac_mode(HVACMode.HEAT)

        mock_api.async_set_room_state.assert_called_once()
        assert entity._attr_preset_mode is None

    @pytest.mark.asyncio
    async def test_transition_heat_to_auto(
        self, climate_entity_factory, mock_api
    ):
        """Transitioning from HEAT to AUTO clears override."""
        overrides = {"room_123": {"mode": API_MODE_MANUAL, "temp": 22.0}}
        entity = climate_entity_factory(overrides=overrides)

        await entity.async_set_hvac_mode(HVACMode.AUTO)

        assert "room_123" not in overrides
        assert entity._attr_preset_mode == PRESET_SCHEDULE

    @pytest.mark.asyncio
    async def test_multiple_preset_changes(
        self, climate_entity_factory, mock_api
    ):
        """Multiple preset changes update override correctly."""
        overrides = {}
        entity = climate_entity_factory(overrides=overrides)

        # Set boost
        await entity.async_set_preset_mode(PRESET_BOOST)
        assert overrides["room_123"]["mode"] == API_MODE_BOOST

        # Change to away
        await entity.async_set_preset_mode(PRESET_AWAY)
        assert overrides["room_123"]["mode"] == API_MODE_AWAY

        # Back to schedule (clears)
        await entity.async_set_preset_mode(PRESET_SCHEDULE)
        assert "room_123" not in overrides

    @pytest.mark.asyncio
    async def test_api_failure_propagates(
        self, climate_entity_factory, mock_api
    ):
        """API failure propagates exception."""
        mock_api.async_set_room_state = AsyncMock(side_effect=Exception("API Error"))
        entity = climate_entity_factory()

        with pytest.raises(Exception, match="API Error"):
            await entity.async_set_temperature(temperature=23.0)

    def test_device_info_returns_attr(
        self, climate_entity_factory
    ):
        """device_info property returns _attr_device_info."""
        entity = climate_entity_factory()

        result = entity.device_info

        assert result == entity._attr_device_info
