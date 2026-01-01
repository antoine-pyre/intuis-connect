# Schedule Management

This document describes the schedule management implementation for the Intuis Connect integration, including the API endpoints used, data models, and Home Assistant services.

## Overview

The Intuis Connect system uses a weekly schedule to control heating zones. Each schedule consists of:

- **Timetable**: A list of time slots defining when each zone starts
- **Zones**: Temperature presets (e.g., Night, Day, Eco, Comfort+)
- **Away/Frost temperatures**: Default temperatures for away mode and frost protection

## Schedule Data Model

### Timetable Entry

Each timetable entry marks the **start** of a zone period:

```json
{
  "zone_id": 1,
  "m_offset": 0
}
```

- `zone_id`: The ID of the zone to activate
- `m_offset`: Minutes from Monday 00:00 (0-10079)

**m_offset calculation:**
```
m_offset = (day * 1440) + (hours * 60) + minutes
```

Where `day` is 0-6 (Monday=0, Sunday=6).

**Examples:**
| Day | Time | m_offset |
|-----|------|----------|
| Monday | 00:00 | 0 |
| Monday | 06:00 | 360 |
| Monday | 22:00 | 1320 |
| Tuesday | 06:00 | 1800 |
| Sunday | 22:00 | 10000 |

### Zone

A zone defines temperature settings for each room:

```json
{
  "id": 1,
  "name": "Night",
  "type": 1,
  "rooms_temp": [
    {"room_id": "2060444554", "temp": 17},
    {"room_id": "3263989395", "temp": 16}
  ]
}
```

### Zone Types

| Type | Description |
|------|-------------|
| 0 | Comfort |
| 1 | Night |
| 4 | Day |
| 5 | Eco |
| 8 | Comfort+ |

## API Endpoints

### Sync Home Schedule

**POST** `/api/synchomeschedule`

This endpoint creates or updates a schedule. It's used for all schedule modifications.

#### Request Payload

```json
{
  "home_id": "home_id",
  "id": "schedule_id",
  "name": "Planning",
  "type": "therm",
  "timetable": [
    {"zone_id": 1, "m_offset": 0},
    {"zone_id": 6, "m_offset": 360},
    {"zone_id": 1, "m_offset": 1320}
  ],
  "zones": [
    {
      "id": 1,
      "name": "Night",
      "type": 1,
      "rooms_temp": [
        {"room_id": "2060444554", "temp": 17}
      ]
    }
  ],
  "away_temp": 12,
  "hg_temp": 7
}
```

#### Important Constraints

1. **No consecutive duplicate zones**: The API rejects timetables where two consecutive entries have the same `zone_id`
2. **zones must use `rooms_temp`**: Do not include `rooms` array - use only `rooms_temp`
3. **Timetable must be sorted**: Entries should be sorted by `m_offset`

#### Response

```json
{
  "status": "ok",
  "time_exec": 0.123,
  "time_server": 1767195000
}
```

#### Error Responses

```json
{
  "error": {
    "code": 21,
    "message": "two same consecutive zone_id in timetable"
  }
}
```

| Code | Message |
|------|---------|
| 10 | Argument(s) is(are) missing |
| 21 | two same consecutive zone_id in timetable |
| 21 | Cannot mix rooms and rooms_temp in zones |

## Home Assistant Entities

### Sensors

#### Schedule Summary Sensor
`sensor.intuis_home_schedule_summary`

**State**: Current schedule name

**Attributes**:
- `schedule_id`: Unique schedule identifier
- `is_default`: Whether this is the default schedule
- `away_temperature`: Temperature for away mode
- `frost_guard_temperature`: Frost protection temperature
- `zones`: List of available zones with IDs, names, types, and temperatures

#### Current Zone Sensor
`sensor.intuis_home_current_zone`

**State**: Name of the currently active zone

#### Next Zone Change Sensor
`sensor.intuis_home_next_zone_change`

**State**: Timestamp of the next zone change

**Attributes**:
- `next_zone`: Name of the upcoming zone

#### Room Scheduled Temperature
`sensor.<room>_scheduled_temperature`

**State**: Currently scheduled temperature for the room

**Attributes**:
- `zone_id`: Current zone ID
- `zone_name`: Current zone name
- `zone_type`: Zone type number

### Calendar
`calendar.intuis_home_heating_schedule`

Displays the weekly schedule as calendar events with zone names and temperatures.

### Select Entity
`select.intuis_home_active_schedule`

Allows switching between available schedules.

## Home Assistant Services

### intuis_connect.set_schedule_slot

Set a zone for a specific time slot in the active heating schedule.

**Service Data:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| day | int | Yes | Day of week (0=Monday, 6=Sunday) |
| start_time | string | Yes | Start time in HH:MM format |
| zone_id | int | No* | Zone ID to set |
| zone_name | string | No* | Zone name (case-insensitive) |

*Either `zone_id` or `zone_name` must be provided.

**Example:**

```yaml
service: intuis_connect.set_schedule_slot
data:
  day: 3  # Thursday
  start_time: "07:00"
  zone_name: "Night"
```

### intuis_connect.switch_schedule

Switch to a different heating schedule.

**Service Data:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| schedule_id | string | No* | Schedule ID |
| schedule_name | string | No* | Schedule name |

*Either `schedule_id` or `schedule_name` must be provided.

### intuis_connect.refresh_schedules

Force refresh of schedule data from the API.

## Implementation Details

### Preventing Consecutive Duplicates

When setting a schedule slot, the implementation:

1. Retrieves the current timetable
2. Inserts or updates the entry at the specified m_offset
3. Sorts by m_offset
4. Removes consecutive entries with the same zone_id
5. Syncs to the API

```python
# Remove consecutive duplicate zones
cleaned_timetable = []
prev_zone_id = None
for entry in timetable:
    if entry["zone_id"] != prev_zone_id:
        cleaned_timetable.append(entry)
        prev_zone_id = entry["zone_id"]
```

### Zone Payload Format

The API requires zones to use `rooms_temp` format only:

```python
zones_payload = []
for zone in active_schedule.zones:
    zone_data = {
        "id": zone.id,
        "name": zone.name,
        "type": zone.type,
        "rooms_temp": [
            {"room_id": rt.room_id, "temp": rt.temp}
            for rt in zone.rooms_temp
        ]
    }
    zones_payload.append(zone_data)
```

## Usage Examples

### Automation: Set Night Mode at 22:00

```yaml
automation:
  - alias: "Set Night Mode"
    trigger:
      - platform: time
        at: "22:00:00"
    action:
      - service: intuis_connect.set_schedule_slot
        data:
          day: "{{ now().weekday() }}"
          start_time: "22:00"
          zone_name: "Night"
```

### Script: Quick Eco Mode

```yaml
script:
  quick_eco_mode:
    sequence:
      - service: intuis_connect.set_schedule_slot
        data:
          day: "{{ now().weekday() }}"
          start_time: "{{ now().strftime('%H:%M') }}"
          zone_name: "Eco"
```

## Debugging

Enable debug logging for schedule operations:

```yaml
logger:
  default: warning
  logs:
    custom_components.intuis_connect: debug
    custom_components.intuis_connect.intuis_api.api: debug
```

Log messages to look for:
- `Setting zone 'X' (ID: Y) at day Z (m_offset: N)` - Service called
- `Sync schedule payload: {...}` - Payload sent to API
- `Schedule X synced successfully` - API success
- `sync_schedule failed: ...` - API error with details
