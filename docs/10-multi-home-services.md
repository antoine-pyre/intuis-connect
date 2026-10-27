# Multi-home service contracts

All five domain services accept an optional `home_id`. Use the Intuis home ID
stored in the integration's configuration entry, rather than a Home Assistant
config-entry ID. An explicitly empty or whitespace-only ID is rejected; it never
falls back to the first home.

| Service | Without `home_id` | With `home_id` |
|---|---|---|
| `switch_schedule` | First loaded home; warns if several are loaded | Only that home |
| `set_schedule_slot` | First loaded home; warns if several are loaded | Only that home |
| `set_zone_temperature` | First loaded home; warns if several are loaded | Only that home |
| `refresh_schedules` | All loaded homes | Only that home |
| `import_energy_history` | All loaded homes, optionally filtered by room name | Only that home |

The first home is the first loaded eligible config entry. Automations that need
a specific home should always provide `home_id`, since loading order may change.
Names shared by several homes are resolved within the selected home only.

```yaml
service: intuis_connect.switch_schedule
data:
  home_id: "my-second-intuis-home-id"
  schedule_name: "Week"
```

```yaml
service: intuis_connect.set_zone_temperature
data:
  home_id: "my-second-intuis-home-id"
  schedule_name: "Week"
  zone_name: "Eco"
  room_name: "Living Room"
  temperature: 19.5
```

```yaml
service: intuis_connect.set_schedule_slot
data:
  home_id: "my-second-intuis-home-id"
  start_day: "4"
  end_day: "0"
  start_time: "22:00"
  end_time: "06:00"
  zone_name: "Eco"
```

The legacy `day` field still supplies both days when `start_day` or `end_day` is
omitted. The explicit day fields take precedence. Their validation and midnight
semantics are described in [schedule management](07-schedule-management.md).

```yaml
service: intuis_connect.import_energy_history
data:
  home_id: "my-second-intuis-home-id"
  days: 30
  room_name: "Living Room"
```

`days` is an integer from 1 to 730. An empty optional `room_name` means all rooms.
With a home ID, an unknown room is rejected before creating an import manager or
task. Without a home ID, a nonempty room name filters the loaded homes to those
containing that room; none matching is a validation error before any task starts.
Room and zone matching remains case-insensitive; schedule names remain exact.
The safety conditions of the import itself are described in
[safe energy history import](08-safe-energy-history-import.md).

## Current data and validation

Schedule, zone and room inputs are text fields. Their names are validated when the
handler runs against the current target home's data. They are no longer dropdowns
frozen from the first configured home. New or renamed schedules, zones and rooms
become addressable after `refresh_schedules`, without restarting Home Assistant or
re-registering the services. The refresh updates schedule and room definitions in
the existing shared home model.

Unknown homes, schedules, zones and rooms produce a `ServiceValidationError`
before any cloud command starts. Backend transport errors remain visible rather
than being logged as successful commands. The no-target defaults above preserve
existing automations; provide a home ID to remove ambiguity.

## Installation and lifecycle

`services.yaml` and the English/French service translations are static package
files. Setup and refresh never generate or write account-specific names into the
installed component. The integration therefore works with a read-only installed
component while Home Assistant's own storage remains writable.

Services are registered once for the domain. Each invocation takes a snapshot of
loaded entries and resolves current data rather than capturing the first entry.
An entry removed or reloaded while refresh is waiting does not receive its old
response. A command already sent may complete, but its retired coordinator is not
refreshed by the late acknowledgement.

Removing the first entry keeps services available for other loaded homes. A
successful unload of the last entry unregisters all five domain services. A
refused unload leaves them registered. Re-adding an entry registers them again.

## Validation

Regression tests call the actual Home Assistant service registry with active
schemas. They cover both homes with identical names, unknown/blank targets,
no-target defaults, filtered imports before task creation, changed names after
refresh, adding/reloading entries, first/last unload, late acknowledgements and
schema/description/translation field parity. A setup-plus-refresh test emulates
read-only component writes while retaining native temporary Home Assistant Store
and coordinator behavior. Only the transport and platform-loading boundaries are
simulated, and network sockets remain disabled for tests.
