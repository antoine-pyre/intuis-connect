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

Set a room's temperature in an existing zone of a schedule:

```yaml
service: intuis_connect.set_zone_temperature
data:
  schedule_name: "Week"
  zone_name: "Eco"
  room_name: "Living Room"
  temperature: 19.5
```

Each target (schedule, zone, room) is given by its ID (`schedule_id`, `zone_id`,
`room_id`), its name, or both, which must then designate the same target. Zone
and room names are case-insensitive. A name shared by several targets is
refused as ambiguous instead of picking one: use the IDs, as the planning editor
does. IDs appear in the schedule summary sensor attributes.

Both this service and the zone-temperature `number` entities retain half degrees.
Accepted values are finite temperatures from **5 to 30 °C in 0.5 °C steps**.
A value such as 19.25 is rejected; 19.5 is sent and retained as 19.5 rather than
truncated to 19.

### `intuis_connect.refresh_schedules`

Fetch the current home schedules from the cloud. Targeting and lifecycle of
multi-home services are described in [multi-home service contracts](10-multi-home-services.md).

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

## Extended planning services (TheFab21 #22/#24 adaptations)

`set_schedule_slot` accepts optional `schedule_id` and `schedule_name`. Without
both it retains the active schedule default. If both are supplied they must
identify the same schedule in the selected `home_id`; inactive schedules can
be edited without activating them.

`sync_schedule` replaces a complete weekly timetable and/or changes the
schedule's away/frost temperatures. It shares the confirmed mutation lock with
zone services and number entities. Failed writes preserve the previous model.

```yaml
service: intuis_connect.sync_schedule
data:
  home_id: "my-home-id"
  schedule_id: "my-schedule-id"
  timetable:
    - m_offset: 0
      zone_id: 1
    - m_offset: 480
      zone_id: 2
  away_temp: 16.5
  hg_temp: 7.5
```

A timetable contains 1–512 transitions, with unique integer minute offsets in
0–10079 and known zone IDs. A JSON string is also accepted for compatibility
with the original HTML proposal. The weekly wrap inherits its last zone when
there is no offset zero. `away_temp` accepts 5–25 °C and `hg_temp` 5–15 °C,
in half degrees. Omitting the timetable permits temperature-only updates.
An empty save is rejected. Existing fields not supplied are preserved.

The schedule summary includes `home_id`, `room_names`, raw `timetable` and
`weekly_timetable` with all seven days, including inherited 00:00 zones.
Calendar labels and schedule device default names follow renames; user names
and entity/device IDs are retained.

These capabilities adapt TheFab21's proposals
[#22](https://github.com/antoine-pyre/intuis-connect/pull/22) and
[#24](https://github.com/antoine-pyre/intuis-connect/pull/24) to the shared,
transaction-confirmed scheduling path. See [contribution provenance](contribution-provenance.md).

## Bundled planning editor (TheFab21 #17/#22/#24 adaptation)

The editor ships in `resources/planning/` and is served by `planning_view.py` at
`/api/intuis_connect/planning`, with its assets under the same path. Usage,
dashboard setup and migration from manual copies are described in the
[README](../README.md#visual-schedule-editor).

| File | Responsibility |
|---|---|
| `index.html` | Static shell, credit and dialogs; no inline script |
| `planning-core.js` | Pure logic: summary parsing, interval and midnight rules, validation, save sequence, reconciliation |
| `planning-app.js` | Rendering (text only), iframe and REST connections, token handling, polling |
| `planning.css` | Layout and light/dark tokens |

### Distribution

`async_setup` registers the view once per Home Assistant run, whatever the
number of homes; the manifest declares the `http` dependency and YAML
configuration stays config-entry only. HTTP routes cannot be removed from a
running server: after the last home is unloaded the route answers 404, and it
serves again when a home is loaded. Only the four published names are served;
any other path is a 404, never a file lookup.

Files are read in the executor and cached by modification time and size. The
ETag is derived from the content, `Cache-Control: no-cache` makes the browser
revalidate on every load, and a matching `If-None-Match` (strong, weak, list or
`*`) gets a 304. A new integration version therefore replaces the editor without
stale caches. Responses carry a restrictive CSP (`script-src 'self'`,
`frame-ancestors 'self'`), `nosniff` and `no-referrer`. The view does not
allow CORS.

### Authentication boundary

The route needs no authentication because a dashboard iframe cannot send a
bearer token. The shell holds no home data, token or command, and the route
accepts only GET. Everything else uses Home Assistant's authenticated APIs:

- In a dashboard (same-origin iframe, sandbox of HA's frontend), the editor uses
  the parent `hass` object: its states, its entity registry (only
  `intuis_connect` sensors are read) and `callService`. It waits up to 45 seconds
  for Home Assistant to reconnect, with a countdown, then reports the failure.
- In a standalone tab it uses the REST API with an explicit address and a
  long-lived token. The token stays in memory and `sessionStorage`, or
  `localStorage` only with *Remember*. It never appears in URLs or logs. Logout
  also removes the keys used by earlier manual copies. Reading states is retried
  with backoff for at most 45 seconds; commands are never retried. A rejected
  token returns to the connection form.

Cloud names (homes, schedules, zones, rooms) and error messages are rendered as
text nodes, never as HTML.

### Data and save sequence

The editor reads the schedule summary sensors (`home_id`, `home_name`,
`room_names`, raw `timetable`, zones with `room_temperatures`), ignoring
malformed states. Interval edits apply the same rules as `set_schedule_slot`;
a regression test compares `planning-core.js` with `timetable.py` on thousands
of random cases.

A save runs, in order:

1. One `sync_schedule` (`home_id`, `schedule_id`) when the timetable or the
   away/frost temperatures changed. It is atomic for the schedule.
2. One `set_zone_temperature` per changed room (`home_id`, `schedule_id`,
   `zone_id`, `room_id`).

Each acknowledged step enters the confirmed model; a failed step keeps its
change marked as unsaved and is reported with its error. Nothing claims a global
transaction. Edits are refused beforehand when a value is out of range or not a
half degree, or when the room is no longer known to the home. Duplicate names do
not block anything, since every call addresses its targets by ID.

Unsaved edits are never overwritten by state updates. After a save the
coordinator may still publish the previous state, or an intermediate one, for a
few seconds. Such transition states (each value either pre-save or confirmed)
are ignored for up to 20 seconds. Any other difference is treated as an outside
change: the editor follows it when there is nothing to save, or shows a banner
offering to reload. Without a compare-and-swap in the Intuis API, a change made
elsewhere just before saving can still be overwritten.
