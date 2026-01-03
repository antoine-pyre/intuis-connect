# Solution: Import Historical Energy Data to Existing Entity Statistics

## Problem Statement

The previous implementation used `async_add_external_statistics` which created **external statistics** with the format `intuis_connect:room_energy`. These appear separately from the actual sensor entities and are not useful for users who want history on their existing `sensor.{room}_energy` entities.

## The Solution

Use `async_import_statistics` instead of `async_add_external_statistics` with:
- `source="recorder"` (not the integration domain)
- `statistic_id` matching the existing entity ID (e.g., `sensor.living_room_energy`)

This imports data directly into the existing entity's statistics, appearing in the Energy Dashboard as expected.

---

## Technical Comparison

| Aspect | Previous (Wrong) | Correct Solution |
|--------|------------------|------------------|
| Function | `async_add_external_statistics` | `async_import_statistics` |
| Source | `"intuis_connect"` | `"recorder"` |
| Statistic ID | `intuis_connect:room_energy` | `sensor.room_energy` |
| Result | Separate external statistics | Merged with entity statistics |
| Energy Dashboard | May not appear correctly | Works as expected |

---

## Implementation

### Code Example

```python
from homeassistant.components.recorder.statistics import async_import_statistics
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMetaData,
    StatisticMeanType,
)
from homeassistant.const import UnitOfEnergy

async def import_energy_to_existing_entity(
    hass: HomeAssistant,
    entity_id: str,          # e.g., "sensor.living_room_energy"
    entity_name: str,        # e.g., "Living Room Energy"
    historical_data: list,   # List of (datetime, kwh) tuples
    starting_sum: float,     # Last known sum from existing statistics
):
    """Import historical energy data to an existing sensor entity."""

    # Build statistics data with cumulative sum
    statistics = []
    cumulative_sum = starting_sum

    for timestamp, energy_kwh in historical_data:
        cumulative_sum += energy_kwh
        statistics.append(
            StatisticData(
                start=timestamp,
                state=energy_kwh,      # Period value (hourly/daily consumption)
                sum=cumulative_sum,    # Running total
            )
        )

    # Define metadata - use "recorder" as source for internal statistics
    metadata = StatisticMetaData(
        source="recorder",              # KEY: Must be "recorder" for internal stats
        statistic_id=entity_id,         # KEY: Must match existing entity_id
        name=entity_name,
        unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        unit_class="energy",            # Required in HA 2025.11+
        has_sum=True,
        mean_type=StatisticMeanType.NONE,  # Required in HA 2025.11+
    )

    # Import to existing entity statistics
    async_import_statistics(hass, metadata, statistics)
```

### Getting the Starting Sum

Before importing, retrieve the last known sum to avoid spikes:

```python
from homeassistant.components.recorder.statistics import (
    statistics_during_period,
    get_last_statistics,
)

async def get_last_sum(hass: HomeAssistant, entity_id: str) -> float:
    """Get the last sum value from existing statistics."""
    # Get the most recent statistic
    last_stats = await get_instance(hass).async_add_executor_job(
        get_last_statistics,
        hass,
        1,              # number of stats
        entity_id,
        True,           # convert_units
        {"sum"},        # types to retrieve
    )

    if last_stats and entity_id in last_stats:
        return last_stats[entity_id][0].get("sum", 0.0)

    return 0.0
```

---

## Critical Requirements

### 1. Entity Must Exist First

The sensor entity must already exist in Home Assistant before importing statistics. The energy sensors are created during integration setup, so this should be satisfied.

```python
# Verify entity exists
if not hass.states.get(entity_id):
    _LOGGER.error("Entity %s does not exist, cannot import statistics", entity_id)
    return
```

### 2. Entity Must Have state_class

The energy sensor must have `state_class=SensorStateClass.TOTAL_INCREASING` for statistics to be tracked. This is already set in the existing energy sensors.

### 3. Sum Alignment to Avoid Spikes

The `sum` value must be continuous. If existing statistics have `sum=150.5` at the last entry, the first imported entry must continue from there:

```
Existing:  ... sum=148.0 → sum=150.5
Imported:      sum=152.3 → sum=155.1 → ...  (continuing from 150.5)
```

**Wrong (causes spike):**
```
Existing:  ... sum=150.5
Imported:      sum=2.3 → sum=5.1 → ...  (restarting from 0)
```

### 4. Timestamps Must Be UTC and Hourly-Aligned

Statistics are stored hourly. Timestamps should be:
- UTC timezone
- Aligned to hour boundaries (minutes/seconds = 0)

```python
from datetime import datetime, timezone

# Correct: hourly aligned UTC
timestamp = datetime(2024, 1, 15, 14, 0, 0, tzinfo=timezone.utc)

# Wrong: not aligned
timestamp = datetime(2024, 1, 15, 14, 26, 35, tzinfo=timezone.utc)
```

---

## Handling Daily API Data

The Intuis API returns daily energy data, but HA statistics are hourly. Options:

### Option A: Import as Daily (Recommended)

Import one entry per day at midnight. HA handles this correctly for the Energy Dashboard.

```python
for day_data in api_response:
    day_start = datetime.combine(
        day_data["date"],
        datetime.min.time(),
        tzinfo=timezone.utc
    )
    # Import single entry for the day
    statistics.append(StatisticData(
        start=day_start,
        state=day_data["energy_kwh"],
        sum=cumulative_sum,
    ))
```

### Option B: Distribute Across Hours

Split daily consumption into 24 hourly entries (less accurate but more granular).

```python
hourly_energy = day_data["energy_kwh"] / 24
for hour in range(24):
    hour_start = day_start + timedelta(hours=hour)
    cumulative_sum += hourly_energy
    statistics.append(StatisticData(
        start=hour_start,
        state=hourly_energy,
        sum=cumulative_sum,
    ))
```

**Recommendation:** Use Option A (daily) for simplicity and accuracy.

---

## Overwriting Existing Data

The `async_import_statistics` function overwrites existing data for the same timestamps. This means:

- Safe to re-run import for the same period
- Can correct previously imported data
- No duplicate entries created

---

## Implementation Flow

```
┌─────────────────────────────────────────────────────────────┐
│            User Calls Service: import_energy_history        │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                   For Each Room:                            │
│  1. Get entity_id: sensor.{room_slug}_energy                │
│  2. Verify entity exists                                    │
│  3. Get last sum from existing statistics                   │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              Fetch Historical Data from API:                │
│  - api.async_get_energy_measures(room, start, end, "1day")  │
│  - Convert Wh to kWh                                        │
│  - Handle rate limiting (429)                               │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              Build Statistics with Cumulative Sum           │
│  - Start from last_sum                                      │
│  - Add each day's consumption                               │
│  - Create StatisticData entries                             │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│            async_import_statistics()                        │
│  - source="recorder"                                        │
│  - statistic_id=entity_id                                   │
│  - Merges with existing entity statistics                   │
└─────────────────────────────────────────────────────────────┘
```

---

## Potential Issues

### 1. Entity ID Format

The entity ID must exactly match what's registered in HA. Check the current naming pattern:

```python
# If your entities are named like:
entity_id = f"sensor.{room_name_slug}_energy"  # sensor.living_room_energy

# Must match exactly in the import
statistic_id = entity_id
```

### 2. Multiple Energy Sensors

If you have multiple energy sensors per room (e.g., different tariffs), import to each separately.

### 3. First-Time Import

For new installations with no existing statistics, `starting_sum` should be 0.

### 4. Rate Limiting

The Intuis API rate limits requests. Use delays between API calls:

```python
await asyncio.sleep(1.5)  # 1.5 seconds between requests
```

---

## Service Definition

```yaml
import_energy_history:
  name: Import Energy History
  description: >
    Import historical energy data from Intuis cloud to existing sensor entities.
    Data appears on the same sensor.{room}_energy entities used in the Energy Dashboard.
  fields:
    days:
      name: Days to Import
      description: Number of days of history to import (1-730)
      required: true
      default: 365
      selector:
        number:
          min: 1
          max: 730
          mode: box
    room_name:
      name: Room (Optional)
      description: Import only this room. Leave empty for all rooms.
      required: false
      selector:
        select:
          options: []  # Dynamically populated
```

---

## Validation Checklist

Before implementing:

- [ ] Confirm energy sensors exist with correct entity IDs
- [ ] Verify sensors have `state_class=TOTAL_INCREASING`
- [ ] Test `async_import_statistics` with `source="recorder"` works in current HA version
- [ ] Implement sum alignment logic
- [ ] Handle API rate limiting gracefully
- [ ] Add progress tracking for user visibility

---

## Sources

- [homeassistant-statistics Integration](https://github.com/klausj1/homeassistant-statistics) - Reference implementation
- [Spook Recorder Actions](https://spook.boo/recorder/) - `recorder.import_statistics` documentation
- [HA Statistics API Changes](https://developers.home-assistant.io/blog/2025/10/16/recorder-statistics-api-changes/)
- [Long-term Statistics Structure](https://data.home-assistant.io/docs/statistics/)

---

*Generated: 2026-01-02*
