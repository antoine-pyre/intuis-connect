# Support diagnostics and partial history imports

Home Assistant's **Download diagnostics** action on the integration entry
exports a support snapshot. Its design adapts the diagnostics platform by
**adrienvsj**, source revision
[`acc734719c7e0484c949f89fc6d9a1a910c67252`](https://github.com/adrienvsj/intuis-connect/commit/acc734719c7e0484c949f89fc6d9a1a910c67252).
The implementation uses the current import manager rather than the fork's
private hourly anchor storage.

The export includes coordinator availability, polling interval, anonymous room
state, schedule counts, hourly updater presence and the most recent **daily**
import report. Each report identifies the requested closed-day period, received
sample count, measured dates, imported days, unmeasured days, sensor registration,
status and failure stage (`fetch`, `validation` or `recorder`). Errors are exported
as class names, without their potentially sensitive messages. A missing day is
not a fabricated zero: existing statistics for unmeasured days are preserved.

Room identifiers become local aliases (`room_1`, etc.), shared between room
states, the import report and the planning export. Account credentials, entry
IDs/titles, house name, cloud identifiers, coordinates, city, raw options,
registry entity IDs and exception text are excluded. **Room, schedule and zone
names are now intentionally included in `planning_export` for migration**, along
with temperatures, consumption and import dates; inspect the file before sharing.
Aliases are meaningful only inside one download.

## Export all loaded plannings

After installing the updated beta and restarting Home Assistant, download the
integration diagnostics under **Settings → Devices & services → Intuis Connect →
Download diagnostics**. In the downloaded JSON, `data.planning_export` contains:

- `schema_version`, UTC `captured_at`, home `timezone`, and room alias/name mapping;
- all loaded schedules, **including inactive schedules**, their names, types,
  default/selected flags and local `schedule_N` references;
- complete `timetable` transitions (`m_offset`: minutes from Monday 00:00,
  `zone_id`: the local zone ID), including the Sunday-to-Monday cycle;
- all zones, including unused zones, with both `rooms_temp` temperatures and
  `rooms` thermostat temperatures/pilot-wire orders kept separately;
- away/frost temperatures for heating, tariff fields/prices for electricity,
  and DHW states with consistent local module aliases for event schedules.

The model held by the coordinator takes priority over the initial setup model,
so a refreshed planning is exported. This operation makes no cloud request,
changes no setpoint and does not require selecting each schedule. It exports
what the integration has already loaded: check `coordinator.last_update_success`
and refresh the schedules before downloading if needed. Data discarded by the
model parser, unknown cloud fields, physical module associations, historical
energy series and HA automation definitions are not part of this planning export.
It is not a full account backup and does not automatically install HA schedules.

For the planned deprecation and the local migration workflow, see the
[Zigbee2MQTT migration guide (FR)](16-zigbee-migration.md). Export and check every
schedule before removing the first radiator from Intuis.

The output uses allowlisted model fields, not raw API replies or object internals.
Missing room definitions retain their alias with a null name. Original cloud
IDs cannot be reconstructed from this file; the room names let you map schedules
to the new Zigbee entities when migrating.

The per-room report lives in memory until the entry is reloaded. It is replaced
by the next daily import, including a targeted retry, and is explicitly labeled
`last_daily_run`: it does not claim to describe hourly imports or cost recalculation.

When some rooms fail, the daily import reports `partial` if others succeeded.
Each successful room commits independently; failed rooms retain their statistics.
Use `intuis_connect.import_energy_history` with `home_id`, `room_name` and a short
`days` period to retry one affected room, then download diagnostics before reloading.
Empty rooms without equipment are excluded by the existing importer.

Offline regression coverage includes six equipped rooms with two successful
transactions and four fetch failures, preservation of all failed-room rows in
the actual HA recorder, and a targeted retry that changes only the selected room.
These checks do not establish whether a particular cloud account has historical
measurements for the requested dates.
