# Unit Test Plan - Intuis Connect Integration

## Overview

This document outlines the unit test system for the Intuis Connect Home Assistant integration.
Tests are organized by module and use pytest with mocking to isolate components.

---

## Directory Structure

```
tests/
├── __init__.py
├── conftest.py                 # Shared fixtures
├── PLAN.md                     # This file
│
├── unit/                       # Unit tests (mocked, fast)
│   ├── __init__.py
│   ├── test_intuis_data.py     # IntuisData class tests
│   ├── test_climate.py         # Climate entity tests
│   ├── test_api.py             # API client tests
│   ├── test_overrides.py       # Override/sticky system tests
│   ├── test_schedule_helpers.py # Schedule manipulation helpers
│   └── test_mapper.py          # Data mapping tests
│
└── integration/                # Integration tests (real API, slow)
    ├── __init__.py
    └── ... (existing tests moved here)
```

---

## Test Dependencies

Add to `requirements_dev.txt`:
```
pytest>=7.0.0
pytest-asyncio>=0.21.0
pytest-cov>=4.0.0
pytest-mock>=3.10.0
aioresponses>=0.7.4
freezegun>=1.2.0
```

---

## Shared Fixtures (conftest.py)

### Mock Objects

```python
@pytest.fixture
def mock_hass():
    """Mock Home Assistant instance."""

@pytest.fixture
def mock_api():
    """Mock IntuisAPI with configurable responses."""

@pytest.fixture
def mock_coordinator():
    """Mock DataUpdateCoordinator."""

@pytest.fixture
def sample_room():
    """Sample IntuisRoom for testing."""

@pytest.fixture
def sample_override():
    """Sample override dict."""

@pytest.fixture
def sample_schedule():
    """Sample IntuisThermSchedule."""
```

### Time Control

```python
@pytest.fixture
def frozen_time():
    """Freeze time for deterministic tests."""
```

---

## Test Cases by Module

### 1. test_overrides.py - Override/Sticky System

**Priority: HIGH** (Most bugs found here)

#### Test Class: `TestOverrideCreation`
| Test | Description |
|------|-------------|
| `test_set_temperature_creates_override` | Setting temp creates override with correct fields |
| `test_set_preset_away_creates_override` | Away preset creates override with away_temp |
| `test_set_preset_boost_creates_override` | Boost preset creates override with boost_temp |
| `test_override_has_last_reapply` | Override includes last_reapply timestamp |
| `test_override_persisted_to_storage` | Override is saved via callback |

#### Test Class: `TestOverrideClearing`
| Test | Description |
|------|-------------|
| `test_hvac_auto_clears_override` | Setting AUTO mode clears override |
| `test_hvac_off_clears_override` | Setting OFF mode clears override |
| `test_preset_schedule_clears_override` | Schedule preset clears override |
| `test_clearing_persists_to_storage` | Clearing triggers storage save |

#### Test Class: `TestIndefiniteMode`
| Test | Description |
|------|-------------|
| `test_reapply_within_buffer_window` | Re-applies when within 5min of expiry |
| `test_no_reapply_outside_buffer` | No re-apply when >5min until expiry |
| `test_no_reapply_before_min_interval` | No re-apply within 2min of last reapply |
| `test_reapply_updates_end_timestamp` | end_ts extended after re-apply |
| `test_reapply_updates_last_reapply` | last_reapply updated after re-apply |
| `test_reapply_api_failure_no_update` | Timestamps not updated on API failure |
| `test_already_expired_reapplies_immediately` | Expired override re-applies on next cycle |

#### Test Class: `TestNonIndefiniteMode`
| Test | Description |
|------|-------------|
| `test_expired_override_cleared` | Override removed after end_ts passes |
| `test_active_override_not_cleared` | Override kept while end_ts in future |
| `test_clearing_persists_to_storage` | Clearing triggers storage save |

#### Test Class: `TestOverridePersistence`
| Test | Description |
|------|-------------|
| `test_overrides_loaded_on_startup` | Stored overrides loaded into memory |
| `test_overrides_saved_on_change` | Changes trigger storage save |
| `test_empty_storage_returns_empty_dict` | No stored data returns {} |

#### Test Class: `TestOverrideEdgeCases`
| Test | Description |
|------|-------------|
| `test_orphaned_override_for_removed_room` | Override for non-existent room |
| `test_override_with_zero_end_ts` | Corrupted end_ts=0 |
| `test_override_with_missing_fields` | Partial override data |
| `test_toggle_indefinite_mode_while_active` | Mode change mid-override |
| `test_duration_changed_in_settings` | Settings change during override |
| `test_api_failure_on_set_temperature` | API fails when creating override |
| `test_concurrent_override_changes` | Multiple rapid changes |

---

### 2. test_intuis_data.py - Data Handler

#### Test Class: `TestAsyncUpdate`
| Test | Description |
|------|-------------|
| `test_fetches_home_status` | Calls API for home status |
| `test_processes_room_data` | Extracts room data correctly |
| `test_daily_reset_clears_counters` | Counters reset on new day |
| `test_returns_expected_structure` | Return dict has correct keys |

#### Test Class: `TestEnergyFetching`
| Test | Description |
|------|-------------|
| `test_daily_scale_cached` | Daily data cached after fetch |
| `test_realtime_scale_not_cached` | Real-time data always fresh |
| `test_before_2am_skipped_daily` | No fetch before 2 AM (daily) |
| `test_wh_to_kwh_conversion` | Converts Wh to kWh correctly |

---

### 3. test_climate.py - Climate Entity

#### Test Class: `TestClimateState`
| Test | Description |
|------|-------------|
| `test_hvac_mode_off` | Returns OFF for off mode |
| `test_hvac_mode_auto` | Returns AUTO for home/auto mode |
| `test_hvac_mode_heat` | Returns HEAT for manual/away/boost |
| `test_preset_mode_mapping` | Correct preset for each mode |
| `test_hvac_action_heating` | HEATING when room is heating |
| `test_hvac_action_idle` | IDLE when not heating |

#### Test Class: `TestClimateActions`
| Test | Description |
|------|-------------|
| `test_set_temperature_calls_api` | API called with correct params |
| `test_set_hvac_mode_calls_api` | API called for mode change |
| `test_set_preset_mode_calls_api` | API called for preset change |
| `test_coordinator_refresh_after_action` | Refresh triggered after action |

---

### 4. test_schedule_helpers.py - Schedule Manipulation

#### Test Class: `TestFindZoneAtOffset`
| Test | Description |
|------|-------------|
| `test_finds_zone_at_exact_offset` | Exact match returns correct zone |
| `test_finds_zone_before_offset` | Returns most recent zone before offset |
| `test_wraps_around_week` | Returns last zone for week wrap |
| `test_empty_timetable` | Returns 0 for empty timetable |

#### Test Class: `TestUpsertTimetableEntry`
| Test | Description |
|------|-------------|
| `test_inserts_new_entry` | Adds entry if offset not exists |
| `test_updates_existing_entry` | Updates zone_id if offset exists |

#### Test Class: `TestRemoveConsecutiveDuplicates`
| Test | Description |
|------|-------------|
| `test_removes_duplicates` | Consecutive same zones removed |
| `test_keeps_different_zones` | Different zones kept |
| `test_empty_timetable` | Returns [] for empty |
| `test_single_entry` | Single entry unchanged |

#### Test Class: `TestSetScheduleSlot`
| Test | Description |
|------|-------------|
| `test_same_day_slot` | Monday 08:00-22:00 |
| `test_multi_day_slot` | Friday 22:00 - Monday 06:00 |
| `test_midnight_end_same_day` | Monday 18:00 - 00:00 |
| `test_midnight_end_different_day` | Monday 18:00 - Tuesday 00:00 |
| `test_restores_previous_zone` | End entry has correct zone |

---

### 5. test_api.py - API Client

#### Test Class: `TestAuthentication`
| Test | Description |
|------|-------------|
| `test_refresh_token_success` | Token refresh works |
| `test_refresh_token_invalid` | InvalidAuth on bad token |
| `test_token_auto_refresh` | Refreshes before expiry |

#### Test Class: `TestAPIRequests`
| Test | Description |
|------|-------------|
| `test_get_homes_data` | Fetches and parses homes |
| `test_get_home_status` | Fetches room status |
| `test_set_room_state` | Sets room mode/temp |
| `test_sync_schedule` | Syncs schedule to API |

#### Test Class: `TestAPIErrors`
| Test | Description |
|------|-------------|
| `test_network_error_raises` | CannotConnect on network fail |
| `test_auth_error_raises` | InvalidAuth on 401 |
| `test_retry_on_transient_error` | Retries on 500 |

---

## Running Tests

```bash
# Run all unit tests
pytest tests/unit/ -v

# Run with coverage
pytest tests/unit/ --cov=custom_components/intuis_connect --cov-report=html

# Run specific test file
pytest tests/unit/test_overrides.py -v

# Run specific test
pytest tests/unit/test_overrides.py::TestIndefiniteMode::test_reapply_within_buffer_window -v

# Run integration tests (requires real credentials)
pytest tests/integration/ -v --integration
```

---

## Mocking Strategy

### API Mocking
```python
@pytest.fixture
def mock_api(mocker):
    api = mocker.Mock(spec=IntuisAPI)
    api.async_set_room_state = mocker.AsyncMock(return_value=None)
    api.async_get_home_status = mocker.AsyncMock(return_value={...})
    return api
```

### Time Mocking
```python
from freezegun import freeze_time

@freeze_time("2024-01-15 10:00:00")
def test_something():
    now = int(time.time())  # Always 2024-01-15 10:00:00
```

### Storage Mocking
```python
@pytest.fixture
def mock_storage(mocker):
    store = mocker.Mock()
    store.async_load = mocker.AsyncMock(return_value={"overrides": {}})
    store.async_save = mocker.AsyncMock(return_value=None)
    return store
```

---

## Coverage Goals

| Module | Target Coverage |
|--------|-----------------|
| `intuis_data.py` | 90% |
| `climate.py` | 85% |
| `__init__.py` (services) | 80% |
| `api.py` | 75% |
| Overall | 80% |

---

## Implementation Priority

1. **Phase 1**: Core fixtures and test infrastructure
2. **Phase 2**: Override system tests (highest bug density)
3. **Phase 3**: Climate entity tests
4. **Phase 4**: Schedule helper tests
5. **Phase 5**: API tests
6. **Phase 6**: Integration tests migration

---

## CI Integration

Add to `.github/workflows/tests.yml`:
```yaml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements_dev.txt
      - run: pytest tests/unit/ --cov --cov-report=xml
      - uses: codecov/codecov-action@v3
```
