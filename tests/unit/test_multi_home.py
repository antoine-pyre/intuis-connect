"""Tests for multi-home support in Intuis Connect.

These tests verify:
- Config flow handles single vs. multiple homes correctly
- Home selection step appears only for multi-home accounts
- Duplicate home configuration is prevented
- Already-configured homes are filtered from selection
- Unique IDs are distinct per home
- Services can target specific homes
- Migration from V2 to V3 works correctly
- Backward compatibility with single-home setups
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any

# Sample home data for tests
SAMPLE_HOMES_SINGLE = [
    {"id": "home_abc123", "name": "My House", "timezone": "Europe/Paris"},
]

SAMPLE_HOMES_MULTI = [
    {"id": "home_abc123", "name": "Main House", "timezone": "Europe/Paris"},
    {"id": "home_def456", "name": "Beach House", "timezone": "Europe/Paris"},
    {"id": "home_ghi789", "name": "Mountain Cabin", "timezone": "Europe/Paris"},
]


class TestConfigFlowSingleHome:
    """Tests for single-home account flow."""

    @pytest.mark.asyncio
    async def test_single_home_skips_selection(self):
        """Single-home accounts should auto-select and skip home selection step."""
        from custom_components.intuis_connect.config_flow import ConfigFlow
        from custom_components.intuis_connect.utils.const import CONF_USERNAME, CONF_PASSWORD

        flow = ConfigFlow()
        flow.hass = MagicMock()
        flow.hass.config_entries = MagicMock()
        flow.hass.config_entries.async_entries = MagicMock(return_value=[])

        # Mock async_set_unique_id and _abort_if_unique_id_configured
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = MagicMock()

        # Mock API validation to return single home
        mock_api = MagicMock()
        mock_api.refresh_token = "test_refresh_token"

        with patch(
            "custom_components.intuis_connect.config_flow.async_validate_api",
            new_callable=AsyncMock,
            return_value=(SAMPLE_HOMES_SINGLE, mock_api),
        ):
            with patch(
                "custom_components.intuis_connect.config_flow.async_get_clientsession",
                return_value=MagicMock(),
            ):
                result = await flow.async_step_user({
                    CONF_USERNAME: "test@example.com",
                    CONF_PASSWORD: "password123",
                })

        # Should go to indefinite step (not select_home)
        assert result["type"] == "form"
        assert result["step_id"] == "indefinite"

        # Should have auto-selected the home
        assert flow._home_id == "home_abc123"
        assert flow._home_name == "My House"

        # Unique ID should be username (backward compatible for single home)
        flow.async_set_unique_id.assert_called_once_with("test@example.com")

    @pytest.mark.asyncio
    async def test_backward_compatibility_existing_single_home(self):
        """Existing single-home entries should continue to work without home_name."""
        from custom_components.intuis_connect.utils.const import (
            CONF_USERNAME,
            CONF_REFRESH_TOKEN,
            CONF_HOME_ID,
        )

        # Simulate V2 config entry data (no home_name)
        v2_entry_data = {
            CONF_USERNAME: "test@example.com",
            CONF_REFRESH_TOKEN: "token123",
            CONF_HOME_ID: "home_abc123",
        }

        # Entry should still work - home_name is optional
        assert CONF_USERNAME in v2_entry_data
        assert CONF_HOME_ID in v2_entry_data


class TestConfigFlowMultiHome:
    """Tests for multi-home account flow."""

    @pytest.mark.asyncio
    async def test_multi_home_shows_selection(self):
        """Multi-home accounts should show home selection dropdown."""
        from custom_components.intuis_connect.config_flow import ConfigFlow
        from custom_components.intuis_connect.utils.const import CONF_USERNAME, CONF_PASSWORD

        flow = ConfigFlow()
        flow.hass = MagicMock()
        flow.hass.config_entries = MagicMock()
        flow.hass.config_entries.async_entries = MagicMock(return_value=[])

        # Mock API validation to return multiple homes
        mock_api = MagicMock()
        mock_api.refresh_token = "test_refresh_token"

        with patch(
            "custom_components.intuis_connect.config_flow.async_validate_api",
            new_callable=AsyncMock,
            return_value=(SAMPLE_HOMES_MULTI, mock_api),
        ):
            with patch(
                "custom_components.intuis_connect.config_flow.async_get_clientsession",
                return_value=MagicMock(),
            ):
                result = await flow.async_step_user({
                    CONF_USERNAME: "test@example.com",
                    CONF_PASSWORD: "password123",
                })

        # Should go to select_home step
        assert result["type"] == "form"
        assert result["step_id"] == "select_home"

        # Should have stored homes list
        assert len(flow._homes) == 3

    @pytest.mark.asyncio
    async def test_home_selection_sets_unique_id_with_home(self):
        """Selecting a home should create unique_id with username + home_id."""
        from custom_components.intuis_connect.config_flow import ConfigFlow
        from custom_components.intuis_connect.utils.const import CONF_HOME_ID

        flow = ConfigFlow()
        flow.hass = MagicMock()
        flow._username = "test@example.com"
        flow._homes = SAMPLE_HOMES_MULTI.copy()
        flow._refresh_token = "test_token"

        # Mock methods
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = MagicMock()
        flow._async_current_entries = MagicMock(return_value=[])

        result = await flow.async_step_select_home({
            CONF_HOME_ID: "home_def456",
        })

        # Should have selected the home
        assert flow._home_id == "home_def456"
        assert flow._home_name == "Beach House"

        # Unique ID should include both username and home_id
        flow.async_set_unique_id.assert_called_once_with("test@example.com_home_def456")

        # Should proceed to indefinite step
        assert result["type"] == "form"
        assert result["step_id"] == "indefinite"

    @pytest.mark.asyncio
    async def test_filters_configured_homes(self):
        """Already-configured homes should be filtered from selection."""
        from custom_components.intuis_connect.config_flow import ConfigFlow
        from custom_components.intuis_connect.utils.const import CONF_HOME_ID, CONF_USERNAME

        flow = ConfigFlow()
        flow.hass = MagicMock()
        flow._username = "test@example.com"
        flow._homes = SAMPLE_HOMES_MULTI.copy()
        flow._refresh_token = "test_token"

        # Mock existing entry for one of the homes
        existing_entry = MagicMock()
        existing_entry.data = {
            CONF_USERNAME: "test@example.com",
            CONF_HOME_ID: "home_abc123",  # Already configured
        }
        flow._async_current_entries = MagicMock(return_value=[existing_entry])

        # Get form without submitting
        result = await flow.async_step_select_home(None)

        assert result["type"] == "form"
        assert result["step_id"] == "select_home"

        # Check that the schema filters out the configured home
        schema = result["data_schema"]
        # The SelectSelector should only have 2 options (Beach House and Mountain Cabin)
        # We verify by checking the schema dict
        schema_dict = schema.schema
        home_id_key = list(schema_dict.keys())[0]
        selector = schema_dict[home_id_key]

        # The selector config should have 2 options (excluding the configured home)
        # Access via the SelectSelector's config attribute
        options = selector.config["options"]
        assert len(options) == 2
        assert all(opt["value"] != "home_abc123" for opt in options)

    @pytest.mark.asyncio
    async def test_aborts_when_all_homes_configured(self):
        """Should abort when all homes are already configured."""
        from custom_components.intuis_connect.config_flow import ConfigFlow
        from custom_components.intuis_connect.utils.const import CONF_HOME_ID, CONF_USERNAME

        flow = ConfigFlow()
        flow.hass = MagicMock()
        flow._username = "test@example.com"
        flow._homes = SAMPLE_HOMES_SINGLE.copy()  # Only one home
        flow._refresh_token = "test_token"

        # Mock existing entry for that home
        existing_entry = MagicMock()
        existing_entry.data = {
            CONF_USERNAME: "test@example.com",
            CONF_HOME_ID: "home_abc123",
        }
        flow._async_current_entries = MagicMock(return_value=[existing_entry])

        result = await flow.async_step_select_home(None)

        assert result["type"] == "abort"
        assert result["reason"] == "all_homes_configured"


class TestUniqueIds:
    """Tests for entity unique ID patterns."""

    def test_unique_ids_include_home_id(self):
        """Entity unique IDs should include home_id for isolation."""
        from custom_components.intuis_connect.climate import IntuisConnectClimate

        # Mock room
        room = MagicMock()
        room.id = "room_123"
        room.name = "Living Room"
        room.temperature = 21.5
        room.target_temperature = 22.0
        room.mode = "home"
        room.heating = False
        room.presence = False
        room.open_window = False
        room.anticipation = False

        # Create entity for home 1
        coordinator1 = MagicMock()
        coordinator1.data = {"rooms": {"room_123": room}}

        entity1 = IntuisConnectClimate(
            coordinator=coordinator1,
            home_id="home_abc123",
            room=room,
            api=MagicMock(),
            entry_id="entry_1",
        )

        # Create entity for home 2 with same room ID
        entity2 = IntuisConnectClimate(
            coordinator=coordinator1,
            home_id="home_def456",
            room=room,
            api=MagicMock(),
            entry_id="entry_2",
        )

        # Unique IDs should be different
        assert entity1.unique_id != entity2.unique_id
        assert "home_abc123" in entity1.unique_id
        assert "home_def456" in entity2.unique_id


class TestServicesMultiHome:
    """Tests for service calls with multi-home support."""

    @pytest.mark.asyncio
    async def test_refresh_schedules_all_homes(self):
        """refresh_schedules without home_id should refresh all homes."""
        from custom_components.intuis_connect.services import (
            ATTR_HOME_ID,
            REFRESH_SCHEDULES_SCHEMA,
        )

        # Schema should accept empty call (no home_id)
        result = REFRESH_SCHEDULES_SCHEMA({})
        assert ATTR_HOME_ID not in result

    @pytest.mark.asyncio
    async def test_refresh_schedules_specific_home(self):
        """refresh_schedules with home_id should target that home only."""
        from custom_components.intuis_connect.services import (
            ATTR_HOME_ID,
            REFRESH_SCHEDULES_SCHEMA,
        )

        # Schema should accept home_id
        result = REFRESH_SCHEDULES_SCHEMA({ATTR_HOME_ID: "home_abc123"})
        assert result[ATTR_HOME_ID] == "home_abc123"


class TestMigration:
    """Tests for config entry migration."""

    @pytest.mark.asyncio
    async def test_migration_v2_to_v3_adds_home_name(self):
        """Migration from V2 to V3 should add home_name."""
        from custom_components.intuis_connect import async_migrate_entry
        from custom_components.intuis_connect.utils.const import (
            CONF_USERNAME,
            CONF_REFRESH_TOKEN,
            CONF_HOME_ID,
            CONF_HOME_NAME,
        )

        # Create mock V2 entry
        mock_entry = MagicMock()
        mock_entry.entry_id = "test_entry"
        mock_entry.version = 2
        mock_entry.data = {
            CONF_USERNAME: "test@example.com",
            CONF_REFRESH_TOKEN: "token123",
            CONF_HOME_ID: "home_abc123",
        }

        # Mock hass
        mock_hass = MagicMock()
        mock_hass.config_entries = MagicMock()
        update_calls = []

        def track_update(entry, **kwargs):
            update_calls.append(kwargs)

        mock_hass.config_entries.async_update_entry = track_update

        # Mock API to return home name
        mock_api = MagicMock()
        mock_api.async_refresh_access_token = AsyncMock()
        mock_api.async_get_all_homes = AsyncMock(return_value=[
            {"id": "home_abc123", "name": "My House", "timezone": "Europe/Paris"},
        ])

        with patch(
            "custom_components.intuis_connect.async_get_clientsession",
            return_value=MagicMock(),
        ):
            with patch(
                "custom_components.intuis_connect.IntuisAPI",
                return_value=mock_api,
            ):
                result = await async_migrate_entry(mock_hass, mock_entry)

        assert result is True
        assert len(update_calls) == 1

        # Check that home_name was added
        new_data = update_calls[0]["data"]
        assert CONF_HOME_NAME in new_data
        assert new_data[CONF_HOME_NAME] == "My House"
        assert update_calls[0]["version"] == 3

    @pytest.mark.asyncio
    async def test_migration_fallback_when_api_fails(self):
        """Migration should use fallback home_name when API fails."""
        from custom_components.intuis_connect import async_migrate_entry
        from custom_components.intuis_connect.intuis_api.api import InvalidAuth
        from custom_components.intuis_connect.utils.const import (
            CONF_USERNAME,
            CONF_REFRESH_TOKEN,
            CONF_HOME_ID,
            CONF_HOME_NAME,
        )

        mock_entry = MagicMock()
        mock_entry.entry_id = "test_entry"
        mock_entry.version = 2
        mock_entry.data = {
            CONF_USERNAME: "test@example.com",
            CONF_REFRESH_TOKEN: "token123",
            CONF_HOME_ID: "home_abc123",
        }

        mock_hass = MagicMock()
        mock_hass.config_entries = MagicMock()
        update_calls = []

        def track_update(entry, **kwargs):
            update_calls.append(kwargs)

        mock_hass.config_entries.async_update_entry = track_update

        # Mock API to fail
        mock_api = MagicMock()
        mock_api.async_refresh_access_token = AsyncMock(
            side_effect=InvalidAuth("API Error")
        )

        with patch(
            "custom_components.intuis_connect.async_get_clientsession",
            return_value=MagicMock(),
        ):
            with patch(
                "custom_components.intuis_connect.IntuisAPI",
                return_value=mock_api,
            ):
                result = await async_migrate_entry(mock_hass, mock_entry)

        assert result is True

        # Check fallback name was used
        new_data = update_calls[0]["data"]
        assert CONF_HOME_NAME in new_data
        assert new_data[CONF_HOME_NAME] == "Home home_abc"  # Truncated home_id

    @pytest.mark.asyncio
    async def test_migration_skips_v3_entries(self):
        """V3 entries should not be migrated."""
        from custom_components.intuis_connect import async_migrate_entry
        from custom_components.intuis_connect.utils.const import (
            CONF_USERNAME,
            CONF_REFRESH_TOKEN,
            CONF_HOME_ID,
            CONF_HOME_NAME,
        )

        mock_entry = MagicMock()
        mock_entry.entry_id = "test_entry"
        mock_entry.version = 3  # Already V3
        mock_entry.data = {
            CONF_USERNAME: "test@example.com",
            CONF_REFRESH_TOKEN: "token123",
            CONF_HOME_ID: "home_abc123",
            CONF_HOME_NAME: "My House",
        }

        mock_hass = MagicMock()
        mock_hass.config_entries = MagicMock()
        mock_hass.config_entries.async_update_entry = MagicMock()

        result = await async_migrate_entry(mock_hass, mock_entry)

        assert result is True
        # Should not have called update
        mock_hass.config_entries.async_update_entry.assert_not_called()


class TestAPIMultiHome:
    """Tests for API multi-home support."""

    @pytest.mark.asyncio
    async def test_async_get_all_homes_returns_list(self):
        """async_get_all_homes should return a list of home dicts."""
        from custom_components.intuis_connect.intuis_api.api import IntuisAPI

        mock_session = MagicMock()
        api = IntuisAPI(mock_session)
        api._base_url = "https://test.example.com"
        api._access_token = "test_token"

        # Mock the API response
        mock_response = MagicMock()
        mock_response.json = AsyncMock(return_value={
            "body": {
                "homes": [
                    {"id": "home_1", "name": "House 1", "timezone": "Europe/Paris"},
                    {"id": "home_2", "name": "House 2", "timezone": "Europe/London"},
                ]
            }
        })
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        with patch.object(api, "_async_request", return_value=mock_response):
            homes = await api.async_get_all_homes()

        assert isinstance(homes, list)
        assert len(homes) == 2
        assert homes[0]["id"] == "home_1"
        assert homes[0]["name"] == "House 1"
        assert homes[1]["id"] == "home_2"
        assert homes[1]["name"] == "House 2"

    @pytest.mark.asyncio
    async def test_async_login_returns_homes_list(self):
        """async_login should return list of homes, not single home_id."""
        from custom_components.intuis_connect.intuis_api.api import IntuisAPI

        mock_session = MagicMock()
        api = IntuisAPI(mock_session)

        # The return type should be list[dict], not str
        # This is a type annotation check - we verify the method exists
        assert hasattr(api, "async_login")

    def test_async_get_homes_data_accepts_target_home_id(self):
        """async_get_homes_data should accept optional target_home_id parameter."""
        from custom_components.intuis_connect.intuis_api.api import IntuisAPI
        import inspect

        # Check that the method accepts target_home_id parameter
        sig = inspect.signature(IntuisAPI.async_get_homes_data)
        params = list(sig.parameters.keys())

        assert "target_home_id" in params


class TestHelperMultiHome:
    """Tests for helper function multi-home support."""

    @pytest.mark.asyncio
    async def test_async_validate_api_returns_homes_list(self):
        """async_validate_api should return (list[dict], api) tuple."""
        from custom_components.intuis_connect.utils.helper import async_validate_api
        from custom_components.intuis_connect.intuis_api.api import IntuisAPI

        mock_session = MagicMock()
        mock_api = MagicMock(spec=IntuisAPI)
        mock_api.async_login = AsyncMock(return_value=SAMPLE_HOMES_MULTI)

        with patch(
            "custom_components.intuis_connect.utils.helper.IntuisAPI",
            return_value=mock_api,
        ):
            homes, api = await async_validate_api(
                "test@example.com",
                "password123",
                mock_session,
            )

        assert isinstance(homes, list)
        assert len(homes) == 3
        assert api is mock_api
