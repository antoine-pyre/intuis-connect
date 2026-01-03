# Historical Energy Import in Home Assistant: Complete Research

This document provides comprehensive research on importing historical energy data into Home Assistant, specifically for the Intuis Connect integration.

---

## Executive Summary

**Previous Attempt:** This integration had a working implementation (commit `810b81a08`) that was later removed (commit `82720211`) due to "Home Assistant limitations."

**Current Status:** The approach used was technically correct, but faced practical issues with:
1. Rate limiting from the Intuis API
2. External statistics visibility in Energy Dashboard
3. API deprecations requiring updates

**Recommendation:** Re-implement using the updated HA statistics API with a service-based approach for better user control.

---

## How Home Assistant Stores Historical Data

### Database Structure

| Table | Purpose | Retention |
|-------|---------|-----------|
| `states` | Raw entity state history | Purged after ~10 days |
| `statistics_short_term` | 5-minute snapshots | Purged after ~10 days |
| `statistics` | Hourly aggregates | Never purged |
| `statistics_meta` | Metadata for statistics | Never purged |

### Statistics Types

**Measurement sensors** (temperature, humidity):
- Store: `min`, `max`, `mean`
- State class: `measurement`

**Metered sensors** (energy, water, gas):
- Store: `state` (period value), `sum` (cumulative total)
- State class: `total` or `total_increasing`
- Required for Energy Dashboard

### Statistic ID Format

- **Entity statistics:** `sensor.room_energy` (period as separator)
- **External statistics:** `intuis_connect:room_energy` (colon as separator)

---

## Methods to Import Historical Data

### Method 1: `async_add_external_statistics` (Recommended for Integrations)

The official HA API for integrations to import external historical data.

```python
from homeassistant.components.recorder.statistics import async_add_external_statistics
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMetaData,
    StatisticMeanType,
)
from homeassistant.const import UnitOfEnergy

# Define metadata (updated for HA 2025.11+)
metadata = StatisticMetaData(
    source="intuis_connect",
    statistic_id="intuis_connect:living_room_energy",
    name="Living Room Energy",
    unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    unit_class="energy",           # NEW: Required in 2025.11+
    has_sum=True,
    mean_type=StatisticMeanType.NONE,  # NEW: Replaces has_mean
)

# Prepare data points
statistics = [
    StatisticData(
        start=datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc),
        state=5.2,      # Daily consumption in kWh
        sum=5.2,        # Cumulative total
    ),
    StatisticData(
        start=datetime(2024, 1, 2, 0, 0, tzinfo=timezone.utc),
        state=4.8,
        sum=10.0,       # Previous sum + current state
    ),
]

# Import into database
async_add_external_statistics(hass, metadata, statistics)
```

**Pros:**
- Official HA API, well-supported
- Works with Energy Dashboard
- Database-agnostic (SQLite, MariaDB, PostgreSQL)

**Cons:**
- External statistics may not appear in all UI contexts
- Requires careful sum calculation
- Must handle API deprecations

### Method 2: Historical Sensor Module (`ha-historical-sensor`)

A Python module for creating sensors that write historical states directly.

```python
from homeassistant_historical_sensor import (
    HistoricalSensor,
    HistoricalState,
    PollUpdateMixin,
)

class IntuisHistoricalEnergySensor(PollUpdateMixin, HistoricalSensor, SensorEntity):
    """Sensor that imports historical energy data."""

    async def async_update_historical(self):
        """Fetch and store historical states."""
        # Fetch from API
        history = await self.api.get_energy_history(days=30)

        # Convert to HistoricalState objects
        self._attr_historical_states = [
            HistoricalState(
                state=entry["energy_kwh"],
                dt=entry["timestamp"],
            )
            for entry in history
        ]

    @property
    def statistic_id(self):
        return self.entity_id

    def get_statistic_metadata(self):
        return {"has_sum": True}

    async def async_calculate_statistic_data(self, start, end):
        # Calculate statistics from historical states
        ...
```

**Pros:**
- Integrates with existing sensor entities
- Automatic polling support
- Works well for ongoing imports

**Cons:**
- Additional dependency
- More complex implementation
- Sensor shows "undefined" state

### Method 3: Service-Based Import (User-Triggered)

Expose a service that users can call to trigger import.

```python
async def async_setup_services(hass, entry):
    async def handle_import_history(call):
        """Handle import_history service call."""
        days = call.data.get("days", 365)
        room = call.data.get("room")  # Optional filter

        # Perform import with progress updates
        await async_import_energy_history(hass, entry, days, room)

    hass.services.async_register(
        DOMAIN,
        "import_energy_history",
        handle_import_history,
        schema=vol.Schema({
            vol.Optional("days", default=365): vol.Range(min=1, max=730),
            vol.Optional("room"): str,
        }),
    )
```

**Pros:**
- User controls when import happens
- Can specify date range
- Avoids automatic rate limiting issues

**Cons:**
- User must manually trigger
- No progress visibility in UI

---

## API Deprecation Timeline

### Python API (affects integrations)

| Parameter | Status | Deadline |
|-----------|--------|----------|
| `has_mean` | Deprecated | HA 2025.11 |
| `mean_type` | Required | HA 2025.11 |
| `unit_class` | Required | HA 2025.11 |

### WebSocket API (affects frontend/tools)

| Parameter | Status | Deadline |
|-----------|--------|----------|
| `has_mean` | Deprecated | HA 2026.11 |
| `mean_type` | Required | HA 2026.11 |
| `unit_class` | Required | HA 2026.11 |

### StatisticMeanType Values

```python
from homeassistant.components.recorder.models import StatisticMeanType

StatisticMeanType.NONE       # 0 - No mean (energy sensors)
StatisticMeanType.ARITHMETIC # 1 - Standard average
StatisticMeanType.CIRCULAR   # 2 - For angular data (wind direction)
```

---

## Previous Implementation Analysis

The removed implementation (commit `810b81a08`) had:

### What Worked

1. **Persistent State Management**
   - Used `homeassistant.helpers.storage.Store` for progress tracking
   - Could resume after restart or rate limiting

2. **Per-Room Processing**
   - Tracked completion status per room
   - Maintained cumulative sums correctly

3. **Rate Limiting Handling**
   - Detected 429 errors
   - Saved progress before stopping
   - Added delays between requests (1.5s)

### What Failed

1. **Background Execution**
   - Ran during `async_setup_entry` without user consent
   - No visibility into progress
   - Could cause unexpected load

2. **External Statistics Visibility**
   - Statistics appeared under `intuis_connect:room_energy`
   - May not have integrated well with Energy Dashboard entity picker

3. **API Deprecations**
   - Used deprecated `has_mean=False` parameter
   - Missing required `unit_class` parameter

4. **User Experience**
   - No way to see progress
   - No way to stop/restart
   - No error notifications

---

## Recommended Implementation Strategy

### Approach: Service-Based with Progress Entity

Create a service for user-triggered import with a progress sensor.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    User Triggers Service                     │
│              intuis_connect.import_energy_history            │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                  HistoryImportManager                        │
│  - Loads/saves progress from persistent storage              │
│  - Tracks per-room completion                                │
│  - Handles rate limiting                                     │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                    Intuis API                                │
│  - async_get_energy_measures(rooms, start, end, scale)       │
│  - Returns Wh per room per day                               │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              async_add_external_statistics                   │
│  - Writes to statistics table                                │
│  - Uses statistic_id: "intuis_connect:room_name_energy"      │
└─────────────────────────────────────────────────────────────┘
```

### Key Features

1. **User-Initiated Import**
   - Service: `intuis_connect.import_energy_history`
   - Parameters: `days` (1-730), `room` (optional filter)

2. **Progress Tracking**
   - Diagnostic sensor: `sensor.intuis_import_progress`
   - Attributes: `current_room`, `rooms_completed`, `total_rooms`, `days_imported`, `status`

3. **Resumable Operation**
   - Persists progress to `.storage/intuis_connect.import_state`
   - Automatically resumes on service call after rate limiting

4. **Rate Limit Handling**
   - Exponential backoff on 429 errors
   - 2-second delay between API calls
   - Saves progress before pausing

5. **Updated API Usage**
   ```python
   metadata = StatisticMetaData(
       source=DOMAIN,
       statistic_id=f"{DOMAIN}:{room_slug}_energy",
       name=f"{room_name} Energy",
       unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
       unit_class="energy",
       has_sum=True,
       mean_type=StatisticMeanType.NONE,
   )
   ```

### Service Definition

```yaml
# services.yaml
import_energy_history:
  name: Import Energy History
  description: Import historical energy data from Intuis cloud into Home Assistant statistics.
  fields:
    days:
      name: Days
      description: Number of days to import (1-730)
      required: false
      default: 365
      selector:
        number:
          min: 1
          max: 730
          step: 1
          mode: box
    room_name:
      name: Room
      description: Specific room to import (leave empty for all rooms)
      required: false
      selector:
        select:
          options: []  # Dynamically populated
```

### Progress Sensor

```python
class IntuisImportProgressSensor(SensorEntity):
    """Sensor showing energy history import progress."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:database-import"

    @property
    def native_value(self):
        """Return current status."""
        return self._manager.status  # "idle", "importing", "rate_limited", "completed"

    @property
    def extra_state_attributes(self):
        return {
            "current_room": self._manager.current_room,
            "rooms_completed": self._manager.rooms_completed,
            "total_rooms": self._manager.total_rooms,
            "days_imported": self._manager.days_imported,
            "total_days": self._manager.total_days,
            "last_error": self._manager.last_error,
            "estimated_remaining": self._manager.estimated_remaining,
        }
```

---

## Energy Dashboard Integration

### External Statistics Visibility

External statistics (`intuis_connect:room_energy`) appear in:
- Developer Tools > Statistics
- History panel with statistic ID
- Energy Dashboard "Add device" (may require manual entry)

### Linking to Existing Sensors

To make imported history appear on existing sensors, use the same `statistic_id`:

```python
# Option 1: Match existing sensor entity_id
statistic_id = "sensor.living_room_energy"  # Same as entity

# Option 2: External statistics (separate from live sensor)
statistic_id = "intuis_connect:living_room_energy_history"
```

**Recommendation:** Use external statistics to avoid conflicts with live sensors.

---

## Alternative Approaches

### 1. File-Based Import (homeassistant-statistics)

Users export Intuis data to CSV, then import via the community integration.

**Pros:** No rate limiting, user controls timing
**Cons:** Manual process, requires data conversion

### 2. Direct Database Access (Home-Assistant-Import-Energy-Data)

SQL scripts to insert historical data directly.

**Pros:** Fast, handles large datasets
**Cons:** Risky, requires database access, not supported

### 3. Export Service for External Tools

Provide a service that exports Intuis data to CSV for use with other tools.

```yaml
export_energy_history:
  name: Export Energy History
  description: Export energy data to CSV file for import with other tools.
```

---

## Implementation Checklist

- [ ] Update `StatisticMetaData` to use `mean_type` and `unit_class`
- [ ] Create `import_energy_history` service
- [ ] Add progress tracking sensor (diagnostic)
- [ ] Implement persistent storage for resume capability
- [ ] Add rate limiting with exponential backoff
- [ ] Update `services.yaml` with dynamic room options
- [ ] Add translations for service and sensor
- [ ] Test with Energy Dashboard
- [ ] Document in README

---

## Sources

- [Home Assistant Statistics API Changes (Oct 2025)](https://developers.home-assistant.io/blog/2025/10/16/recorder-statistics-api-changes/)
- [Long- and Short-term Statistics](https://data.home-assistant.io/docs/statistics/)
- [homeassistant-statistics Integration](https://github.com/klausj1/homeassistant-statistics)
- [Home-Assistant-Import-Energy-Data](https://github.com/patrickvorgers/Home-Assistant-Import-Energy-Data)
- [ha-historical-sensor Module](https://github.com/ldotlopez/ha-historical-sensor)
- [Community Discussion: Import Historical Energy Data](https://community.home-assistant.io/t/how-to-import-historical-energy-data/556356)

---

*Generated: 2026-01-02*
