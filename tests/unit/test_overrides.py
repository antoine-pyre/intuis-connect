"""Tests for the override/sticky system in IntuisData."""
from __future__ import annotations

import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch
from freezegun import freeze_time

# Import the module under test
from custom_components.intuis_connect.intuis_data import (
    IntuisData,
    INDEFINITE_REAPPLY_BUFFER,
    MIN_REAPPLY_INTERVAL,
)
from custom_components.intuis_connect.utils.const import (
    API_MODE_MANUAL,
    API_MODE_AWAY,
    API_MODE_BOOST,
)


# ---------------------------------------------------------------------------
# Test: Indefinite Mode Re-application
# ---------------------------------------------------------------------------

class TestIndefiniteMode:
    """Tests for indefinite mode override re-application."""

    @pytest.mark.asyncio
    async def test_reapply_within_buffer_window(
        self,
        intuis_data_factory,
        mock_api,
        mock_save_overrides,
        sample_room_data,
        indefinite_mode_options,
        get_options_factory,
    ):
        """Override should re-apply when within buffer window and past min interval."""
        now = int(time.time())
        overrides = {
            "room_123": {
                "mode": API_MODE_MANUAL,
                "temp": 23.0,
                "end": now + 120,  # 2 minutes until expiry (within 5 min buffer)
                "sticky": True,
                "last_reapply": now - 180,  # 3 minutes ago (past 2 min interval)
            }
        }

        intuis_data = intuis_data_factory(
            overrides=overrides,
            options=indefinite_mode_options,
            api=mock_api,
            save_callback=mock_save_overrides,
        )

        # Mock the API calls in async_update
        mock_api.async_get_home_status.return_value = {"body": {"home": {"id": "home_123", "rooms": [], "modules": []}}}

        # Patch extract_rooms to return our sample room
        with patch(
            "custom_components.intuis_connect.intuis_data.extract_rooms",
            return_value=sample_room_data,
        ), patch(
            "custom_components.intuis_connect.intuis_data.extract_modules",
            return_value={},
        ), patch(
            "custom_components.intuis_connect.intuis_data.IntuisHomeConfig.from_dict",
            return_value=MagicMock(),
        ):
            await intuis_data.async_update()

        # Verify API was called to re-apply
        mock_api.async_set_room_state.assert_called_once_with(
            "room_123",
            API_MODE_MANUAL,
            23.0,
            5,  # DEFAULT_MANUAL_DURATION
        )

        # Verify timestamps were updated
        assert overrides["room_123"]["end"] > now
        assert overrides["room_123"]["last_reapply"] >= now

        # Verify storage was saved
        mock_save_overrides.assert_called()

    @pytest.mark.asyncio
    async def test_no_reapply_outside_buffer(
        self,
        intuis_data_factory,
        mock_api,
        mock_save_overrides,
        sample_room_data,
        indefinite_mode_options,
    ):
        """Override should NOT re-apply when far from expiry."""
        now = int(time.time())
        overrides = {
            "room_123": {
                "mode": API_MODE_MANUAL,
                "temp": 23.0,
                "end": now + 600,  # 10 minutes until expiry (outside 5 min buffer)
                "sticky": True,
                "last_reapply": now - 180,
            }
        }

        intuis_data = intuis_data_factory(
            overrides=overrides,
            options=indefinite_mode_options,
            api=mock_api,
            save_callback=mock_save_overrides,
        )

        mock_api.async_get_home_status.return_value = {"body": {"home": {"id": "home_123", "rooms": [], "modules": []}}}

        with patch(
            "custom_components.intuis_connect.intuis_data.extract_rooms",
            return_value=sample_room_data,
        ), patch(
            "custom_components.intuis_connect.intuis_data.extract_modules",
            return_value={},
        ), patch(
            "custom_components.intuis_connect.intuis_data.IntuisHomeConfig.from_dict",
            return_value=MagicMock(),
        ):
            await intuis_data.async_update()

        # API should NOT be called
        mock_api.async_set_room_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_reapply_before_min_interval(
        self,
        intuis_data_factory,
        mock_api,
        mock_save_overrides,
        sample_room_data,
        indefinite_mode_options,
    ):
        """Override should NOT re-apply if recently re-applied (within 2 min)."""
        now = int(time.time())
        overrides = {
            "room_123": {
                "mode": API_MODE_MANUAL,
                "temp": 23.0,
                "end": now + 120,  # Within buffer
                "sticky": True,
                "last_reapply": now - 60,  # Only 1 minute ago (within 2 min interval)
            }
        }

        intuis_data = intuis_data_factory(
            overrides=overrides,
            options=indefinite_mode_options,
            api=mock_api,
            save_callback=mock_save_overrides,
        )

        mock_api.async_get_home_status.return_value = {"body": {"home": {"id": "home_123", "rooms": [], "modules": []}}}

        with patch(
            "custom_components.intuis_connect.intuis_data.extract_rooms",
            return_value=sample_room_data,
        ), patch(
            "custom_components.intuis_connect.intuis_data.extract_modules",
            return_value={},
        ), patch(
            "custom_components.intuis_connect.intuis_data.IntuisHomeConfig.from_dict",
            return_value=MagicMock(),
        ):
            await intuis_data.async_update()

        # API should NOT be called (too soon since last reapply)
        mock_api.async_set_room_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_reapply_already_expired(
        self,
        intuis_data_factory,
        mock_api,
        mock_save_overrides,
        sample_room_data,
        indefinite_mode_options,
    ):
        """Already expired override should re-apply immediately in indefinite mode."""
        now = int(time.time())
        overrides = {
            "room_123": {
                "mode": API_MODE_MANUAL,
                "temp": 23.0,
                "end": now - 60,  # Already expired 1 minute ago
                "sticky": True,
                "last_reapply": now - 300,  # 5 minutes ago
            }
        }

        intuis_data = intuis_data_factory(
            overrides=overrides,
            options=indefinite_mode_options,
            api=mock_api,
            save_callback=mock_save_overrides,
        )

        mock_api.async_get_home_status.return_value = {"body": {"home": {"id": "home_123", "rooms": [], "modules": []}}}

        with patch(
            "custom_components.intuis_connect.intuis_data.extract_rooms",
            return_value=sample_room_data,
        ), patch(
            "custom_components.intuis_connect.intuis_data.extract_modules",
            return_value={},
        ), patch(
            "custom_components.intuis_connect.intuis_data.IntuisHomeConfig.from_dict",
            return_value=MagicMock(),
        ):
            await intuis_data.async_update()

        # Should re-apply (time_until_expiry is negative, which is <= BUFFER)
        mock_api.async_set_room_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_reapply_api_failure_no_timestamp_update(
        self,
        intuis_data_factory,
        mock_save_overrides,
        sample_room_data,
        indefinite_mode_options,
    ):
        """On API failure, timestamps should NOT be updated."""
        now = int(time.time())
        original_end = now + 120
        original_last_reapply = now - 180

        overrides = {
            "room_123": {
                "mode": API_MODE_MANUAL,
                "temp": 23.0,
                "end": original_end,
                "sticky": True,
                "last_reapply": original_last_reapply,
            }
        }

        # Create failing API
        from custom_components.intuis_connect.intuis_api.api import APIError
        failing_api = MagicMock()
        failing_api.async_set_room_state = AsyncMock(side_effect=APIError("API Error"))
        failing_api.async_get_home_status = AsyncMock(
            return_value={"body": {"home": {"id": "home_123", "rooms": [], "modules": []}}}
        )
        failing_api.async_get_config = AsyncMock(return_value={})
        failing_api.async_get_energy_measures = AsyncMock(return_value={})

        intuis_data = intuis_data_factory(
            overrides=overrides,
            options=indefinite_mode_options,
            api=failing_api,
            save_callback=mock_save_overrides,
        )

        with patch(
            "custom_components.intuis_connect.intuis_data.extract_rooms",
            return_value=sample_room_data,
        ), patch(
            "custom_components.intuis_connect.intuis_data.extract_modules",
            return_value={},
        ), patch(
            "custom_components.intuis_connect.intuis_data.IntuisHomeConfig.from_dict",
            return_value=MagicMock(),
        ):
            await intuis_data.async_update()

        # Timestamps should NOT be updated
        assert overrides["room_123"]["end"] == original_end
        assert overrides["room_123"]["last_reapply"] == original_last_reapply


# ---------------------------------------------------------------------------
# Test: Non-Indefinite Mode (Normal Expiry)
# ---------------------------------------------------------------------------

class TestNonIndefiniteMode:
    """Tests for non-indefinite mode override expiry."""

    @pytest.mark.asyncio
    async def test_expired_override_cleared(
        self,
        intuis_data_factory,
        mock_api,
        mock_save_overrides,
        sample_room_data,
        default_options,
    ):
        """Expired override should be removed in non-indefinite mode."""
        now = int(time.time())
        overrides = {
            "room_123": {
                "mode": API_MODE_MANUAL,
                "temp": 23.0,
                "end": now - 60,  # Expired 1 minute ago
                "sticky": True,
                "last_reapply": now - 300,
            }
        }

        intuis_data = intuis_data_factory(
            overrides=overrides,
            options=default_options,  # indefinite_mode = False
            api=mock_api,
            save_callback=mock_save_overrides,
        )

        mock_api.async_get_home_status.return_value = {"body": {"home": {"id": "home_123", "rooms": [], "modules": []}}}

        with patch(
            "custom_components.intuis_connect.intuis_data.extract_rooms",
            return_value=sample_room_data,
        ), patch(
            "custom_components.intuis_connect.intuis_data.extract_modules",
            return_value={},
        ), patch(
            "custom_components.intuis_connect.intuis_data.IntuisHomeConfig.from_dict",
            return_value=MagicMock(),
        ):
            await intuis_data.async_update()

        # Override should be removed
        assert "room_123" not in overrides

        # Storage should be saved
        mock_save_overrides.assert_called()

        # API should NOT be called (no re-apply in non-indefinite mode)
        mock_api.async_set_room_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_active_override_not_cleared(
        self,
        intuis_data_factory,
        mock_api,
        mock_save_overrides,
        sample_room_data,
        default_options,
    ):
        """Active override should NOT be removed before expiry."""
        now = int(time.time())
        overrides = {
            "room_123": {
                "mode": API_MODE_MANUAL,
                "temp": 23.0,
                "end": now + 300,  # 5 minutes from now
                "sticky": True,
                "last_reapply": now - 60,
            }
        }

        intuis_data = intuis_data_factory(
            overrides=overrides,
            options=default_options,
            api=mock_api,
            save_callback=mock_save_overrides,
        )

        mock_api.async_get_home_status.return_value = {"body": {"home": {"id": "home_123", "rooms": [], "modules": []}}}

        with patch(
            "custom_components.intuis_connect.intuis_data.extract_rooms",
            return_value=sample_room_data,
        ), patch(
            "custom_components.intuis_connect.intuis_data.extract_modules",
            return_value={},
        ), patch(
            "custom_components.intuis_connect.intuis_data.IntuisHomeConfig.from_dict",
            return_value=MagicMock(),
        ):
            await intuis_data.async_update()

        # Override should still exist
        assert "room_123" in overrides

        # Storage should NOT be saved (no changes)
        mock_save_overrides.assert_not_called()


# ---------------------------------------------------------------------------
# Test: Override Persistence
# ---------------------------------------------------------------------------

class TestOverridePersistence:
    """Tests for override storage persistence."""

    @pytest.mark.asyncio
    async def test_overrides_saved_on_reapply(
        self,
        intuis_data_factory,
        mock_api,
        mock_save_overrides,
        sample_room_data,
        indefinite_mode_options,
    ):
        """Storage should be saved when override is re-applied."""
        now = int(time.time())
        overrides = {
            "room_123": {
                "mode": API_MODE_MANUAL,
                "temp": 23.0,
                "end": now + 120,
                "sticky": True,
                "last_reapply": now - 180,
            }
        }

        intuis_data = intuis_data_factory(
            overrides=overrides,
            options=indefinite_mode_options,
            api=mock_api,
            save_callback=mock_save_overrides,
        )

        mock_api.async_get_home_status.return_value = {"body": {"home": {"id": "home_123", "rooms": [], "modules": []}}}

        with patch(
            "custom_components.intuis_connect.intuis_data.extract_rooms",
            return_value=sample_room_data,
        ), patch(
            "custom_components.intuis_connect.intuis_data.extract_modules",
            return_value={},
        ), patch(
            "custom_components.intuis_connect.intuis_data.IntuisHomeConfig.from_dict",
            return_value=MagicMock(),
        ):
            await intuis_data.async_update()

        mock_save_overrides.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_save_when_no_changes(
        self,
        intuis_data_factory,
        mock_api,
        mock_save_overrides,
        sample_room_data,
        indefinite_mode_options,
    ):
        """Storage should NOT be saved when no override changes occur."""
        now = int(time.time())
        overrides = {
            "room_123": {
                "mode": API_MODE_MANUAL,
                "temp": 23.0,
                "end": now + 600,  # Far from expiry
                "sticky": True,
                "last_reapply": now - 60,
            }
        }

        intuis_data = intuis_data_factory(
            overrides=overrides,
            options=indefinite_mode_options,
            api=mock_api,
            save_callback=mock_save_overrides,
        )

        mock_api.async_get_home_status.return_value = {"body": {"home": {"id": "home_123", "rooms": [], "modules": []}}}

        with patch(
            "custom_components.intuis_connect.intuis_data.extract_rooms",
            return_value=sample_room_data,
        ), patch(
            "custom_components.intuis_connect.intuis_data.extract_modules",
            return_value={},
        ), patch(
            "custom_components.intuis_connect.intuis_data.IntuisHomeConfig.from_dict",
            return_value=MagicMock(),
        ):
            await intuis_data.async_update()

        mock_save_overrides.assert_not_called()


# ---------------------------------------------------------------------------
# Test: Edge Cases
# ---------------------------------------------------------------------------

class TestOverrideEdgeCases:
    """Tests for edge cases in override handling."""

    @pytest.mark.asyncio
    async def test_orphaned_override_for_removed_room(
        self,
        intuis_data_factory,
        mock_api,
        mock_save_overrides,
        indefinite_mode_options,
    ):
        """Override for room not in data_by_room should be cleaned up."""
        now = int(time.time())
        overrides = {
            "room_999": {  # Room doesn't exist in data
                "mode": API_MODE_MANUAL,
                "temp": 23.0,
                "end": now + 120,
                "sticky": True,
                "last_reapply": now - 180,
            }
        }

        intuis_data = intuis_data_factory(
            overrides=overrides,
            options=indefinite_mode_options,
            api=mock_api,
            save_callback=mock_save_overrides,
        )

        mock_api.async_get_home_status.return_value = {"body": {"home": {"id": "home_123", "rooms": [], "modules": []}}}

        # Return empty room data (room_999 doesn't exist)
        with patch(
            "custom_components.intuis_connect.intuis_data.extract_rooms",
            return_value={},  # No rooms
        ), patch(
            "custom_components.intuis_connect.intuis_data.extract_modules",
            return_value={},
        ), patch(
            "custom_components.intuis_connect.intuis_data.IntuisHomeConfig.from_dict",
            return_value=MagicMock(),
        ):
            await intuis_data.async_update()

        # Override should be REMOVED (orphaned cleanup)
        assert "room_999" not in overrides

        # Storage should be saved (override was cleaned up)
        mock_save_overrides.assert_called()

        # API should NOT be called (room doesn't exist)
        mock_api.async_set_room_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_override_with_zero_end_ts(
        self,
        intuis_data_factory,
        mock_api,
        mock_save_overrides,
        sample_room_data,
        default_options,
    ):
        """Override with end_ts=0 should be cleared immediately in non-indefinite mode."""
        overrides = {
            "room_123": {
                "mode": API_MODE_MANUAL,
                "temp": 23.0,
                "end": 0,  # Corrupted/missing
                "sticky": True,
                "last_reapply": 0,
            }
        }

        intuis_data = intuis_data_factory(
            overrides=overrides,
            options=default_options,
            api=mock_api,
            save_callback=mock_save_overrides,
        )

        mock_api.async_get_home_status.return_value = {"body": {"home": {"id": "home_123", "rooms": [], "modules": []}}}

        with patch(
            "custom_components.intuis_connect.intuis_data.extract_rooms",
            return_value=sample_room_data,
        ), patch(
            "custom_components.intuis_connect.intuis_data.extract_modules",
            return_value={},
        ), patch(
            "custom_components.intuis_connect.intuis_data.IntuisHomeConfig.from_dict",
            return_value=MagicMock(),
        ):
            await intuis_data.async_update()

        # Override should be cleared (now > 0)
        assert "room_123" not in overrides

    @pytest.mark.asyncio
    async def test_override_not_sticky(
        self,
        intuis_data_factory,
        mock_api,
        mock_save_overrides,
        sample_room_data,
        indefinite_mode_options,
    ):
        """Override with sticky=False should be ignored."""
        now = int(time.time())
        overrides = {
            "room_123": {
                "mode": API_MODE_MANUAL,
                "temp": 23.0,
                "end": now + 120,
                "sticky": False,  # Not sticky
                "last_reapply": now - 180,
            }
        }

        intuis_data = intuis_data_factory(
            overrides=overrides,
            options=indefinite_mode_options,
            api=mock_api,
            save_callback=mock_save_overrides,
        )

        mock_api.async_get_home_status.return_value = {"body": {"home": {"id": "home_123", "rooms": [], "modules": []}}}

        with patch(
            "custom_components.intuis_connect.intuis_data.extract_rooms",
            return_value=sample_room_data,
        ), patch(
            "custom_components.intuis_connect.intuis_data.extract_modules",
            return_value={},
        ), patch(
            "custom_components.intuis_connect.intuis_data.IntuisHomeConfig.from_dict",
            return_value=MagicMock(),
        ):
            await intuis_data.async_update()

        # API should NOT be called (not sticky)
        mock_api.async_set_room_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_multiple_rooms_one_fails(
        self,
        intuis_data_factory,
        mock_save_overrides,
        indefinite_mode_options,
    ):
        """One room's re-apply failure should not affect other rooms."""
        now = int(time.time())
        overrides = {
            "room_123": {
                "mode": API_MODE_MANUAL,
                "temp": 23.0,
                "end": now + 120,
                "sticky": True,
                "last_reapply": now - 180,
            },
            "room_456": {
                "mode": API_MODE_BOOST,
                "temp": 30.0,
                "end": now + 120,
                "sticky": True,
                "last_reapply": now - 180,
            },
        }

        # Create room data for both rooms
        room1 = MagicMock()
        room1.id = "room_123"
        room2 = MagicMock()
        room2.id = "room_456"
        room_data = {"room_123": room1, "room_456": room2}

        # API that fails on first room, succeeds on second
        call_count = [0]

        from custom_components.intuis_connect.intuis_api.api import APIError
        async def mock_set_room_state(room_id, mode, temp, duration):
            call_count[0] += 1
            if room_id == "room_123":
                raise APIError("API Error for room_123")
            return None

        api = MagicMock()
        api.async_set_room_state = AsyncMock(side_effect=mock_set_room_state)
        api.async_get_home_status = AsyncMock(
            return_value={"body": {"home": {"id": "home_123", "rooms": [], "modules": []}}}
        )
        api.async_get_config = AsyncMock(return_value={})
        api.async_get_energy_measures = AsyncMock(return_value={})

        intuis_data = intuis_data_factory(
            overrides=overrides,
            options=indefinite_mode_options,
            api=api,
            save_callback=mock_save_overrides,
        )

        with patch(
            "custom_components.intuis_connect.intuis_data.extract_rooms",
            return_value=room_data,
        ), patch(
            "custom_components.intuis_connect.intuis_data.extract_modules",
            return_value={},
        ), patch(
            "custom_components.intuis_connect.intuis_data.IntuisHomeConfig.from_dict",
            return_value=MagicMock(),
        ):
            await intuis_data.async_update()

        # Both rooms should have been attempted
        assert call_count[0] == 2

        # room_456 should have updated timestamps, room_123 should not
        # (timestamps depend on success)


# ---------------------------------------------------------------------------
# Test: Mode-specific Durations
# ---------------------------------------------------------------------------

class TestModeSpecificDurations:
    """Tests for correct duration selection per mode."""

    @pytest.mark.asyncio
    async def test_away_mode_uses_away_duration(
        self,
        intuis_data_factory,
        mock_api,
        mock_save_overrides,
        sample_room_data,
        indefinite_mode_options,
    ):
        """Away mode override should use away_duration setting."""
        now = int(time.time())
        overrides = {
            "room_123": {
                "mode": API_MODE_AWAY,
                "temp": 16.0,
                "end": now + 120,
                "sticky": True,
                "last_reapply": now - 180,
            }
        }

        intuis_data = intuis_data_factory(
            overrides=overrides,
            options=indefinite_mode_options,
            api=mock_api,
            save_callback=mock_save_overrides,
        )

        mock_api.async_get_home_status.return_value = {"body": {"home": {"id": "home_123", "rooms": [], "modules": []}}}

        with patch(
            "custom_components.intuis_connect.intuis_data.extract_rooms",
            return_value=sample_room_data,
        ), patch(
            "custom_components.intuis_connect.intuis_data.extract_modules",
            return_value={},
        ), patch(
            "custom_components.intuis_connect.intuis_data.IntuisHomeConfig.from_dict",
            return_value=MagicMock(),
        ):
            await intuis_data.async_update()

        # Should use away_duration (1440 minutes = 24 hours)
        mock_api.async_set_room_state.assert_called_once_with(
            "room_123",
            API_MODE_AWAY,
            16.0,
            1440,
        )

    @pytest.mark.asyncio
    async def test_boost_mode_uses_boost_duration(
        self,
        intuis_data_factory,
        mock_api,
        mock_save_overrides,
        sample_room_data,
        indefinite_mode_options,
    ):
        """Boost mode override should use boost_duration setting."""
        now = int(time.time())
        overrides = {
            "room_123": {
                "mode": API_MODE_BOOST,
                "temp": 30.0,
                "end": now + 120,
                "sticky": True,
                "last_reapply": now - 180,
            }
        }

        intuis_data = intuis_data_factory(
            overrides=overrides,
            options=indefinite_mode_options,
            api=mock_api,
            save_callback=mock_save_overrides,
        )

        mock_api.async_get_home_status.return_value = {"body": {"home": {"id": "home_123", "rooms": [], "modules": []}}}

        with patch(
            "custom_components.intuis_connect.intuis_data.extract_rooms",
            return_value=sample_room_data,
        ), patch(
            "custom_components.intuis_connect.intuis_data.extract_modules",
            return_value={},
        ), patch(
            "custom_components.intuis_connect.intuis_data.IntuisHomeConfig.from_dict",
            return_value=MagicMock(),
        ):
            await intuis_data.async_update()

        # Should use boost_duration (30 minutes)
        mock_api.async_set_room_state.assert_called_once_with(
            "room_123",
            API_MODE_BOOST,
            30.0,
            30,
        )
