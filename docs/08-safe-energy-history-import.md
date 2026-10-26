# Safe energy history import

The import replaces **complete days in the domicile's timezone**, ending at the
start of the current local day. It excludes today's partial consumption. Existing
sensor unique IDs, entity IDs, configuration entries and storage keys are retained.

This page covers the default `granularity: daily`. Hourly imports
(`granularity: hourly`) write separate external series without a live baseline;
see [hourly energy statistics](11-hourly-energy.md).

## Preconditions and recovery

An import requires a registered room energy sensor with recorder metadata in kWh
and a valid **short-term live statistic after the imported period**. On a fresh
installation, let the sensor record its first live statistics (normally after a
recorder compilation cycle), then call `intuis_connect.import_energy_history` again.
The automatic setup attempt may fail safely if these statistics do not exist yet;
it does not silently retry and its one-shot option is consumed without reloading
and cancelling its own task.

This requirement preserves HA's live cumulative baseline: the sensor recorder
continues sums from short-term statistics, not hourly history. Fabricating a new
zero at midnight would be wrong for counters whose reset hour is 02:00.

Every requested closed day must have exactly one finite, nonnegative measurement
at its local-midnight timestamp. A measured zero is valid; empty, missing,
duplicate, shifted-day or malformed measurements are rejected **before mutation**.
Coverage follows calendar days, including 23-hour and 25-hour DST days. Local day
boundaries not aligned with HA's hourly statistics are explicitly refused.

If the cloud returns fixed UTC days instead of the requested local boundaries,
the import refuses the series instead of replacing a mismatched period. Existing
statistics remain available. Correct the API data/period or retry after missing
data becomes available; do not delete recorder history to work around an error.

## Replacement and continuity

`recorder_import.py` queues a custom `RecorderTask` on HA's actual recorder worker.
Inside **one SQLAlchemy transaction**, it reads the old boundary sums, deletes only
the validated interval from hourly and short-term statistics, inserts the validated
daily hourly points (including zero days), and adjusts post-period cumulative sums
by `new_boundary_sum - old_boundary_sum`.

The last sums are read from the most recent hourly or short-term row before each
boundary. The post-period sensor state is a daily counter, not a consumption delta;
it is never added as though it represented the increment since the import end.
Post-period timestamps, states and recorded increments are preserved; only their
cumulative baseline shifts. Pre-period statistics remain unchanged. Reimporting an
identical period produces the same rows and zero additional sum shift.

The metadata row is not changed and the newest short-term anchor survives with its
ID intact, preserving recorder's metadata and latest-row caches. Live statistics
compilation therefore continues from its adjusted sum. If metadata or the live
anchor is missing, incompatible or invalid, the transaction is refused.

The coroutine receives an acknowledgement **after transaction commit or rollback**,
not when a job is merely queued. Insertion/transaction errors roll back deletion
and adjustment together. Unsupported or stopped recorder workers are rejected
before queuing a job that could never acknowledge completion. The adapter is
verified against HA 2024.6.4 and 2026.10.4; future schema changes must be tested
before extending that compatibility claim.

## Progress and cancellation

There is at most one import task per config entry. Concurrent service calls share
a manager published before its first storage await and a single load operation;
the manager reserves its import task synchronously. Results distinguish `completed`, `partial`, `failed`, `rate_limited` and
`cancelled`, with successful-room counts and errors. Progress is persisted only
for committed rooms; it does not serve as an additive baseline for reimports.

Unloading an entry prevents new imports, cancels the cloud task and waits for any
queued/in-flight recorder transaction to acknowledge rollback or commit. A commit
already in progress can finish, but it finishes **before unload returns**. No
further import writes occur after a successful unload. Executor-backed Store loads
and progress saves are also drained rather than detached on cancellation.

The import is transactional per room, not across the entire domicile. An error in
one room does not roll back another room's already-confirmed import. The result
reports that partial outcome explicitly.

## Validation and rollback

The regression tests run real HA recorder threads, queues and temporary SQLite
databases on both supported versions. They inject insertion failures and pause an
INSERT during unload, verify complete rollback, check duplicate imports, preserve
live anchors and invoke HA's actual sensor statistics compiler after replacement.
No real Intuis account or network connection is used.

A code rollback does not undo a completed data import. A failed transaction already
preserves its previous data; after a confirmed import, restore a recorder backup
if a historical dataset itself must be reverted. Never reset entity IDs or delete
statistics to perform a code rollback.
