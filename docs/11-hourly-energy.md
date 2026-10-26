# Hourly energy statistics

The hourly implementation adapts **TheFab21 #17/#22/#24**. Original sources are
linked in [CONTRIBUTORS.md](../CONTRIBUTORS.md); implementation progress is in
[the task journal](pr-integration-progress.md). Features below are implemented
locally and validated offline; they are not part of a published release yet.

## Identity and ownership

Daily sensors, their IDs, TOTAL_INCREASING, reset hour and freshness attributes
remain unchanged. External hourly series use source `intuis_connect` and IDs
`intuis_connect:energy_<digest>`. The digest is the first 32 SHA-256 hexadecimal
characters of compact JSON `[home_id,room_id]` (ASCII escaping enabled).
A home aggregate uses null as room_id; costs use the separate `cost_` prefix.
Entity renames, accented labels and shared room names cannot change identity.

The recorder metadata has sum=true, mean disabled, and kWh units. The new format
uses mean_type/unit_class on HA 2026.10 and has_mean on HA 2024.6. These series
are separate from recorder-owned daily sensor statistics. Energy dashboard device
consumption can select external sum/kWh series after their first confirmed write.
Choose the home aggregate OR its rooms when configuring totals, to avoid counting
the same consumption twice. The precise dashboard configuration is user-owned.

## Prototype validation

The native external import is accepted by both supported workers. The resulting
sum/kWh metadata is listed by recorder and accepted as device consumption by the
energy preferences schema. The daily import suite also exercises the real sensor
statistics compiler. This validates the backend contract, not a manual browser
selection. Tests use an explicit recorder queue barrier: Event on HA 2024.6,
Future on HA 2026.10. Checking an empty queue alone can miss an in-flight job.
Production writes therefore use the acknowledged transaction described below,
never the public enqueue call alone.

## Hourly series versus the `1hour` energy scale

The **Energy Scale** option (`5min`/`30min`/`1hour`/`1day`) only changes how often
the existing daily sensors refresh their live value. It does not import hours and
its recorder statistics stay those of a daily counter. Hourly statistics are a
separate, opt-in feature: closed hours are written to the external series above.
Both can be used together; neither changes the other.

## Collection and validation

Only hours closed for at least 15 minutes are requested, since the cloud may
consolidate late. Timestamps are unique UTC hours, so local DST days have 23 or
25 hours. Requests are split into 42-day chunks; a point repeated at a chunk
boundary is kept once and a contradictory repeat is refused. A period is refused
before any write when an hour is missing, outside the window, misaligned,
negative, non-finite or not numeric, or when the cloud answers with an error or
a malformed body. Zero is a valid measurement; absence is never turned into zero.

## Writing

Each room, then the home total, is replaced in one transaction on the recorder
worker. The metadata row is created inside that transaction, so a failure leaves
no series behind. Sums continue from the last row before the period, and later
hours keep their consumption with a shifted offset. Replaying identical data
rewrites identical rows. The caller is acknowledged only after commit or
rollback; unload waits for that acknowledgement. The series label is fixed when
the series is created: renaming a room keeps the same continuous series and its
initial label.

## Service

`intuis_connect.import_energy_history` accepts `granularity`:

| Value | Aliases | Effect |
|---|---|---|
| `daily` (default) | `1day` | Unchanged daily sensor replacement of closed local days |
| `hourly` | `1hour` | Closed hours of the last `days` days into the external series |

`days` (1–730), `home_id` and `room_name` keep their meaning. With `room_name`,
only that room is written and the home total is left untouched.

```yaml
service: intuis_connect.import_energy_history
data:
  granularity: hourly
  days: 30
```

## Updater and recovery

Enable **Hourly statistics** in the integration options (off by default for new
and existing installations). Each home runs its own updater, every 120 minutes by
default (1, 2, 4 or 6 hours). A cycle re-reads the last 48 closed hours to pick up
late cloud corrections. After an interruption it resumes from the last confirmed
hour found in the recorder, up to 7 days back; older gaps need the service. No
progress file is kept: the recorder is the only source of truth. A cycle that
finds a manual import running is skipped and caught up later. Disabling the
option stops collection and keeps every statistic already written.

## Home total

The home series is the hour-by-hour sum of its rooms, written only when every
room is confirmed for the same hours. If a room fails, the job reports the home
total as incomplete, names the missing rooms, and keeps the last complete total
instead of writing a partial sum. The existing daily home aggregate is unchanged.

## Cloud API

Hourly data comes from `POST /api/getroommeasure` with `scale=1hour`, the
energy measure types used by the daily sensors, and `date_begin`/`date_end` in
UTC seconds. Responses must declare `step_time=3600`. Real cloud behaviour and
device data are not exercised by the offline tests.
