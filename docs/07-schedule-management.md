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
| Sunday | 22:00 | 9960 |

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

### `intuis_connect.set_schedule_slot`

Replace the full interval in the active schedule, including transitions previously
inside that interval. The interval is **[start, end)**: the selected zone starts at
the beginning; the zone originally scheduled at the end is restored there.
Everything outside the interval keeps its previous zone, including week wrap.

| Field | Required | Description |
|---|---|---|
| `start_day` | Yes, unless `day` is supplied | `"0"` Monday through `"6"` Sunday |
| `end_day` | Yes, unless `day` is supplied | End day, with week wrap supported |
| `start_time` | Yes | `HH:MM` or `HH:MM:00`, minute precision |
| `end_time` | Yes | End time, with the midnight rules below |
| `zone_name` | Yes | Existing zone name, case-insensitive |
| `day` | Optional legacy alias | Supplies both days when they are omitted |

For example, this replaces every previous transition between 07:00 and 11:00 on
Monday. An old 08:00 transition will no longer interrupt Eco:

```yaml
service: intuis_connect.set_schedule_slot
data:
  start_day: "0"
  start_time: "07:00"
  end_day: "0"
  end_time: "11:00"
  zone_name: "Eco"
```

A range may cross the week boundary:

```yaml
service: intuis_connect.set_schedule_slot
data:
  start_day: "4"      # Friday
  start_time: "22:00"
  end_day: "0"        # Following Monday
  end_time: "06:00"
  zone_name: "Night"
```

On the **same day**, an end of `00:00` means the end of that day. On a different
end day, `00:00` means the beginning of that day. Thus Sunday 22:00 → Sunday
00:00 ends at the following Monday boundary, serialized as offset 0 rather than
10080. A same-day end before or equal to the start is rejected, except for the
explicit end-of-day midnight rule. Whole-week/equal cyclic boundaries are
rejected as ambiguous. Nonzero seconds, invalid clocks and invalid days are
rejected instead of silently rounded.

### `intuis_connect.set_zone_temperature`

Set a room's temperature in an existing zone of a named schedule:

```yaml
service: intuis_connect.set_zone_temperature
data:
  schedule_name: "Week"
  zone_name: "Eco"
  room_name: "Living Room"
  temperature: 19.5
```

Both this service and the zone-temperature `number` entities retain half degrees.
Accepted values are finite temperatures from **5 to 30 °C in 0.5 °C steps**.
A value such as 19.25 is rejected; 19.5 is sent and retained as 19.5 rather than
truncated to 19.

### `intuis_connect.refresh_schedules`

Fetch the current home schedules from the cloud. Targeting and lifecycle of
multi-home services are described by the dedicated multi-home contract.

## Mutation implementation and failure guarantees

`replace_timetable_interval` in `timetable.py` performs a pure cyclic-week
transformation. It captures the original end zone, removes transitions inside
the interval, inserts the two boundaries, sorts and removes consecutive duplicate
zones. It never modifies its input and supports schedules without an offset-0
entry. The regression suite checks every minute of a complete week to verify the
preservation of the complement.

`schedule_mutations.py` is shared by the service handlers and `number` entities.
The API client owns a typed lock map, one lock per schedule. Each mutation:

1. Acquires the schedule's lock and resolves the latest home/schedule model.
2. Builds a private copy and applies the interval or temperature change.
3. Sends one common payload, using `rooms_temp` only.
4. Resolves the model again and publishes the confirmed copy only after API success.
5. Lets the entry point request a coordinator refresh.

A cloud error leaves the confirmed timetable and temperatures intact and is
returned to the caller. Invalid input is rejected before any command is sent.
Mutations from services and `number` entities serialize on the same client lock;
a waiting edit starts from the first edit's confirmed result, even when a refresh
has replaced the model object during the first request.

These locks coordinate this integration's in-process edits. They cannot provide
a server-side compare-and-swap against simultaneous edits made by other Intuis
clients, because the API does not expose a revision contract here. Entity unique
IDs, configuration and storage formats are unchanged.

## Debugging

```yaml
logger:
  default: warning
  logs:
    custom_components.intuis_connect: debug
    custom_components.intuis_connect.intuis_api.api: debug
```

An API failure is surfaced by the service or entity command; a successful write
is followed by the coordinator refresh. The local model is never changed before
the write is acknowledged.
