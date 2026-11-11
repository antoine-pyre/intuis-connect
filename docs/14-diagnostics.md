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

Room identifiers become local aliases (`room_1`, etc.), shared between the room
states and that import report. Account credentials, entry IDs/titles, house and
room names, cloud identifiers, coordinates, city, raw options, registry entity
IDs and exception text are excluded. The snapshot still contains temperatures,
consumption and import dates; inspect it before sharing. Aliases are meaningful
only inside one download.

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
