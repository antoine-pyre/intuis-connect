"""Shared fixtures for Intuis Connect tests."""
from __future__ import annotations

import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any

# Add the custom_components to the path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Mock Room Data
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_room_data() -> dict[str, Any]:
    """Sample room data as returned by extract_rooms."""
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
    room.boost_status = "disabled"
    room.energy = 0.0
    room.minutes = 0
    room.bridge_id = "bridge_456"
    return {"room_123": room}


@pytest.fixture
def sample_room(sample_room_data):
    """Single sample room."""
    return sample_room_data["room_123"]


# ---------------------------------------------------------------------------
# Mock Override Data
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_override() -> dict[str, Any]:
    """Sample override dict."""
    now = int(time.time())
    return {
        "mode": "manual",
        "temp": 23.0,
        "end": now + 300,  # 5 minutes from now
        "sticky": True,
        "last_reapply": now - 60,  # 1 minute ago
    }


@pytest.fixture
def expired_override() -> dict[str, Any]:
    """Override that has already expired."""
    now = int(time.time())
    return {
        "mode": "manual",
        "temp": 23.0,
        "end": now - 60,  # Expired 1 minute ago
        "sticky": True,
        "last_reapply": now - 300,
    }


@pytest.fixture
def override_near_expiry() -> dict[str, Any]:
    """Override that will expire soon (within buffer)."""
    now = int(time.time())
    return {
        "mode": "manual",
        "temp": 23.0,
        "end": now + 120,  # 2 minutes from now (within 5 min buffer)
        "sticky": True,
        "last_reapply": now - 180,  # 3 minutes ago (past MIN_REAPPLY_INTERVAL)
    }


# ---------------------------------------------------------------------------
# Mock API
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_api():
    """Mock IntuisAPI with default successful responses."""
    api = MagicMock()
    api.async_set_room_state = AsyncMock(return_value=None)
    api.async_get_home_status = AsyncMock(return_value={
        "body": {
            "home": {
                "id": "home_123",
                "rooms": [],
                "modules": [],
            }
        }
    })
    api.async_get_config = AsyncMock(return_value={})
    api.async_get_homes_data = AsyncMock()
    api.async_sync_schedule = AsyncMock(return_value=None)
    api.async_get_energy_measures = AsyncMock(return_value={})
    return api


@pytest.fixture
def mock_api_failing():
    """Mock IntuisAPI that fails on all calls."""
    api = MagicMock()
    api.async_set_room_state = AsyncMock(side_effect=Exception("API Error"))
    api.async_get_home_status = AsyncMock(side_effect=Exception("API Error"))
    return api


# ---------------------------------------------------------------------------
# Mock Storage
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_save_overrides():
    """Mock save_overrides callback."""
    return AsyncMock(return_value=None)


# ---------------------------------------------------------------------------
# Mock Options
# ---------------------------------------------------------------------------

@pytest.fixture
def default_options() -> dict[str, Any]:
    """Default integration options."""
    return {
        "indefinite_mode": False,
        "manual_duration": 5,
        "away_duration": 1440,
        "boost_duration": 30,
        "away_temp": 16.0,
        "boost_temp": 30.0,
        "energy_scale": "1day",
    }


@pytest.fixture
def indefinite_mode_options() -> dict[str, Any]:
    """Options with indefinite mode enabled."""
    return {
        "indefinite_mode": True,
        "manual_duration": 5,
        "away_duration": 1440,
        "boost_duration": 30,
        "away_temp": 16.0,
        "boost_temp": 30.0,
        "energy_scale": "1day",
    }


@pytest.fixture
def get_options_factory():
    """Factory to create get_options callback."""
    def _factory(options: dict) -> callable:
        return lambda: options
    return _factory


# ---------------------------------------------------------------------------
# Mock IntuisHome
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_intuis_home():
    """Mock IntuisHome object."""
    home = MagicMock()
    home.id = "home_123"
    home.name = "My Home"
    home.rooms = []
    home.schedules = []
    return home


# ---------------------------------------------------------------------------
# IntuisData Instance Factory
# ---------------------------------------------------------------------------

@pytest.fixture
def intuis_data_factory(mock_api, mock_intuis_home, mock_save_overrides, get_options_factory, default_options):
    """Factory to create IntuisData instances for testing."""
    from custom_components.intuis_connect.intuis_data import IntuisData

    def _factory(
        overrides: dict | None = None,
        options: dict | None = None,
        api=None,
        save_callback=None,
    ) -> IntuisData:
        return IntuisData(
            api=api or mock_api,
            intuis_home=mock_intuis_home,
            overrides=overrides or {},
            get_options=get_options_factory(options or default_options),
            save_overrides_callback=save_callback or mock_save_overrides,
        )

    return _factory


# ---------------------------------------------------------------------------
# Schedule Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_timetable() -> list[dict]:
    """Sample timetable with multiple entries."""
    return [
        {"m_offset": 0, "zone_id": 1},      # Monday 00:00 - Night
        {"m_offset": 420, "zone_id": 2},    # Monday 07:00 - Comfort
        {"m_offset": 1320, "zone_id": 1},   # Monday 22:00 - Night
        {"m_offset": 1440, "zone_id": 1},   # Tuesday 00:00 - Night
        {"m_offset": 1860, "zone_id": 2},   # Tuesday 07:00 - Comfort
        {"m_offset": 2760, "zone_id": 1},   # Tuesday 22:00 - Night
    ]


@pytest.fixture
def sample_zones() -> list[dict]:
    """Sample zones."""
    return [
        {"id": 1, "name": "Night", "type": 0},
        {"id": 2, "name": "Comfort", "type": 1},
        {"id": 3, "name": "Eco", "type": 2},
    ]


# ---------------------------------------------------------------------------
# Pytest Configuration
# ---------------------------------------------------------------------------

def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test (requires real API)"
    )


@pytest.fixture
def event_loop_policy():
    """Use default event loop policy."""
    import asyncio
    return asyncio.DefaultEventLoopPolicy()
