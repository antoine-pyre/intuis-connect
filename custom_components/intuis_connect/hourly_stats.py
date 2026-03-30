"""Hourly statistics updater for Intuis Connect.

Exact replication of the Node-RED "Prépare les imports (cumul kWh + dédup)" logic.

Architecture:
- Fetches hourly energy from Intuis API: J-1 00:00 local -> now (25-48 h)
- Computes cumulative sums from persistent midnight_bases (never reads HA DB)
- Imports via recorder.async_import_statistics (source="recorder", idempotent)
- Clears the range before importing -> overwrites any recorder auto-stats
- midnight_bases[statistic_id][day_key] = cumulative sum at that day's 00:00 local
  Updated every run as midnight boundaries are crossed.  Pruned to 270 days.
  Allows partial reimport (e.g. last 3 days) to anchor correctly without DB queries.

The matching sensor (sensor.X_energy) must NOT have state_class set,
otherwise the recorder generates competing statistics and the Energy
Dashboard shows spikes.  hourly_stats is the sole writer of statistics
for these entities.

Cumulative-sum algorithm (same as Node-RED):
  1. Priority: hour-to-hour continuity  ->  prevSum + hourly_kwh
  2. Fallback: midnight_bases[statistic_id][day_key] + cumul since midnight
  state = sum = cumulative total (matches Node-RED convention)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import (
    async_import_statistics,
)
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.const import UnitOfEnergy
from homeassistant.helpers.storage import Store

from .utils.const import DOMAIN, HISTORY_IMPORT_KEY

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from .intuis_api.api import IntuisAPI
    from .entity.intuis_home import IntuisHome

_LOGGER = logging.getLogger(__name__)

# Storage
STORAGE_VERSION = 1
STORAGE_KEY_PREFIX = "intuis_connect.hourly_stats_v3_"

# Constants
HOUR_MS = 3_600_000   # 1 h in milliseconds
HOUR_S = 3600         # 1 h in seconds
MIDNIGHT_BASES_MAX_DAYS = 270   # prune entries older than this


class HourlyStatsUpdater:
    """Imports hourly energy statistics from Intuis API into HA recorder.

    Replicates the Node-RED flow:
      1. Fetch hourly data J-1 00:00 local -> now
      2. For each room, compute cumulative sum with continuity priority
      3. Clear + import all stats (idempotent)
      4. Persist anchors (prevSum, prevStart) and base_kwh for next run
    """

    def __init__(
        self,
        hass: HomeAssistant,
        api: IntuisAPI,
        intuis_home: IntuisHome,
        entry_id: str,
        home_id: str | None = None,
        update_interval_minutes: int = 60,
        timezone_str: str = "Europe/Paris",
    ) -> None:
        self._hass = hass
        self._api = api
        self._intuis_home = intuis_home
        self._entry_id = entry_id
        self._home_id = home_id or intuis_home.id
        self._update_interval = update_interval_minutes
        self._timezone = ZoneInfo(timezone_str)
        self._timezone_str = timezone_str

        # Persistent storage (survives restarts)
        self._store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY_PREFIX}{entry_id}")
        self._data: dict[str, Any] = {}
        self._loaded = False

        # Background task
        self._update_task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._update_lock = asyncio.Lock()  # prevents concurrent async_update() runs

        # Optional cost stats updater (set after construction by __init__.py)
        self.cost_updater = None

    # -- Storage -----------------------------------------------------------

    async def load_storage(self) -> None:
        if self._loaded:
            return
        stored = await self._store.async_load()
        if stored:
            self._data = stored
            # Migrate old format (base_kwh + sensor_base) to midnight_bases
            if "base_kwh" in self._data or "sensor_base" in self._data:
                self._migrate_to_midnight_bases()
        else:
            self._data = {
                "midnight_bases": {},  # {statistic_id: {day_key: float}}
                "anchors": {},         # {statistic_id: {"prev_sum": float, "prev_start": int ms}}
            }
        self._loaded = True
        _LOGGER.debug("Loaded hourly stats storage: %s rooms tracked",
                       len(self._data.get("anchors", {})))
        # Publish immediately so sensors have data on startup
        self._publish_sensor_base()

    def _migrate_to_midnight_bases(self) -> None:
        """Migrate old base_kwh + sensor_base storage to midnight_bases dict."""
        from datetime import date, timedelta
        now_local = datetime.now(self._timezone)
        today_key = now_local.strftime("%Y-%m-%d")
        yesterday_key = (now_local - timedelta(days=1)).strftime("%Y-%m-%d")

        mb = self._data.setdefault("midnight_bases", {})
        base_kwh = self._data.pop("base_kwh", {})
        sensor_base = self._data.pop("sensor_base", {})

        for sid, val in sensor_base.items():
            if val:
                mb.setdefault(sid, {})[today_key] = float(val)
        for sid, val in base_kwh.items():
            if val:
                mb.setdefault(sid, {})[yesterday_key] = float(val)

        # Clean up legacy keys
        self._data.pop("rebase_done", None)
        _LOGGER.info("Migrated storage: base_kwh+sensor_base → midnight_bases for %d sensors", len(mb))

    async def _save_storage(self) -> None:
        """Save storage, pruning midnight_bases entries older than MIDNIGHT_BASES_MAX_DAYS."""
        cutoff = (datetime.now(self._timezone) - timedelta(days=MIDNIGHT_BASES_MAX_DAYS)).strftime("%Y-%m-%d")
        mb = self._data.get("midnight_bases", {})
        for sid in mb:
            mb[sid] = {k: v for k, v in mb[sid].items() if k >= cutoff}
        await self._store.async_save(self._data)

    def _publish_sensor_base(self) -> None:
        """Publish today's midnight sum to hass.data[DOMAIN]["sensor_base"].

        sensor.py reads hass.data[DOMAIN]["sensor_base"][entity_id] to compute:
            native_value = sensor_base + daily_energy

        Falls back to anchor prev_sum if today's midnight not yet captured
        (e.g. first run of the day before midnight boundary is processed).
        """
        if DOMAIN not in self._hass.data:
            self._hass.data[DOMAIN] = {}

        today_key = datetime.now(self._timezone).strftime("%Y-%m-%d")
        mb = self._data.get("midnight_bases", {})
        anchors = self._data.get("anchors", {})

        sensor_base: dict[str, float] = {}
        for sid, by_day in mb.items():
            val = by_day.get(today_key)
            if val is not None:
                sensor_base[sid] = val
            elif sid in anchors:
                # Fallback: last known anchor sum until today midnight is captured
                sensor_base[sid] = float(anchors[sid].get("prev_sum", 0))

        self._hass.data[DOMAIN]["sensor_base"] = sensor_base

    # -- Entity lookup -----------------------------------------------------

    def _get_statistic_id(self, room_id: str) -> str | None:
        """Return the entity_id (= statistic_id) for a room's energy sensor."""
        from homeassistant.helpers import entity_registry as er

        unique_id = f"intuis_{self._intuis_home.id}_{room_id}_energy"
        ent_reg = er.async_get(self._hass)
        entity_id = ent_reg.async_get_entity_id("sensor", DOMAIN, unique_id)

        if not entity_id:
            room = self._intuis_home.rooms.get(room_id)
            _LOGGER.warning(
                "Entity not found: unique_id=%s, room=%s",
                unique_id, room.name if room else room_id,
            )
        return entity_id

    # -- Helpers -----------------------------------------------------------

    @staticmethod
    def _snap_to_hour_ms(timestamp_sec: float) -> int:
        """Snap a Unix timestamp (seconds) to the top of the hour, return ms."""
        ms = int(timestamp_sec * 1000)
        return (ms // HOUR_MS) * HOUR_MS

    def _local_day_key(self, timestamp_ms: int) -> str:
        """YYYY-MM-DD in local timezone from milliseconds."""
        dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=self._timezone)
        return dt.strftime("%Y-%m-%d")

    def _local_hour(self, timestamp_ms: int) -> int:
        """Hour (0-23) in local timezone from milliseconds."""
        dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=self._timezone)
        return dt.hour

    # -- Main update -------------------------------------------------------

    async def async_update(self) -> int:
        """Fetch hourly data and import statistics. Returns count imported."""
        # Skip if history import is running
        import_flags = self._hass.data.get(DOMAIN, {}).get(HISTORY_IMPORT_KEY, {})
        if import_flags.get(self._home_id, False):
            _LOGGER.info("History import in progress - skipping hourly stats")
            return 0

        # Prevent concurrent runs (e.g. scheduled loop + immediate post-import trigger)
        if self._update_lock.locked():
            _LOGGER.debug("Hourly stats update already running, skipping")
            return 0

        async with self._update_lock:

            await self.load_storage()

            # Auto-initialize midnight_bases from DB if empty (first run or storage cleared)
            mb = self._data.get("midnight_bases", {})
            if not mb or all(not v for v in mb.values()):
                _LOGGER.info("midnight_bases is empty — auto-initializing from existing statistics")
                await self.async_initialize_base_from_statistics()

            # Time window: J-1 00:00 local -> now
            now_local = datetime.now(self._timezone)
            today_midnight = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
            yesterday_midnight = today_midnight - timedelta(days=1)

            date_begin = int(yesterday_midnight.timestamp())
            date_end = int(now_local.timestamp())

            _LOGGER.info("Fetching hourly data %s -> %s",
                          yesterday_midnight.isoformat(), now_local.isoformat())

            total_imported = 0
            room_hourly_data: dict[str, list[tuple[int, float]]] = {}
            try:
                for room_id, room in self._intuis_home.rooms.items():
                    try:
                        hourly_data = await self._api.async_get_room_energy_hourly(
                            room_id=room_id,
                            date_begin=date_begin,
                            date_end=date_end,
                        )
                        if not hourly_data:
                            _LOGGER.debug("No hourly data for room %s", room_id)
                            continue
                        room_hourly_data[room_id] = hourly_data
                        total_imported += await self._process_room(room_id, hourly_data)
                    except Exception as room_err:
                        _LOGGER.warning("Error for room %s: %s", room_id, room_err)

                await self._save_storage()

                # Publish today midnight sums to hass.data so sensors can read them
                self._publish_sensor_base()

                _LOGGER.info("Imported %d hourly statistics", total_imported)
                # Signal sensors that LTS is fresh — they can now publish their state.
                self._hass.data[DOMAIN]["hourly_stats_ready"] = True

                # Update cost statistics if a cost updater is configured
                if self.cost_updater is not None and room_hourly_data:
                    try:
                        cost_count = await self.cost_updater.async_update(room_hourly_data)
                        self.cost_updater.publish_cost_base()
                        if cost_count:
                            _LOGGER.info("Imported %d cost statistics", cost_count)
                    except Exception as cost_err:
                        _LOGGER.warning("Cost stats update failed: %s", cost_err)

                return total_imported

            except Exception as err:
                _LOGGER.error("Error in hourly stats update: %s", err, exc_info=True)
                return 0

    # -- Process one room (Node-RED "Prepare les imports" logic) -----------

    async def _process_room(
        self, room_id: str, hourly_data: list[tuple[int, float]]
    ) -> int:
        """Process hourly data for a single room.

        Replicates Node-RED exactly:
          - midnight_bases[sid][day_key] from persistent storage (NEVER from HA DB)
          - Priority: hour-to-hour continuity (prevSum + kwh)
          - Fallback: midnight_bases[sid][day_key] + cumul since midnight
          - state = sum = cumulative total (Node-RED convention)
          - change is auto-calculated by HA as sum[n]-sum[n-1]
          - Always rewrite all hours (idempotent)

        midnight_bases is updated for every midnight boundary encountered.
        With the J-1→now window, at most 2 midnights are crossed per run
        (J-1 00:00 and today 00:00), but the fallback dict is shared with
        history_import so partial reimports (any N-day window) find the
        correct anchor for any day without a DB query.
        """
        if not hourly_data:
            return 0

        statistic_id = self._get_statistic_id(room_id)
        if not statistic_id:
            return 0

        # --- Persistent anchors (from previous run) ---
        anchors = self._data.get("anchors", {}).get(statistic_id, {})
        prev_sum = anchors.get("prev_sum")
        prev_start = anchors.get("prev_start")  # ms

        # --- midnight_bases for this sensor ---
        mb_all = self._data.setdefault("midnight_bases", {})
        mb = mb_all.setdefault(statistic_id, {})   # {day_key: float}

        if prev_sum is not None:
            prev_sum = float(prev_sum)
        if prev_start is not None:
            prev_start = int(prev_start)

        _LOGGER.debug(
            "%s: prev_sum=%s, prev_start=%s",
            statistic_id,
            ("%.3f" % prev_sum) if prev_sum is not None else "None",
            prev_start,
        )

        # --- Build stats (exact Node-RED algorithm) ---
        run_kwh_from_midnight = 0.0
        last_day_key = None
        day_base_cache: dict[str, float] = {}
        stats = []

        for timestamp_sec, wh in hourly_data:
            # Validate
            if wh is None or not isinstance(wh, (int, float)) or wh != wh:
                continue
            if wh < 0:
                continue

            # Snap to top of hour (HA requires mm:ss = 00:00)
            start_ms = self._snap_to_hour_ms(timestamp_sec)
            start_dt = datetime.fromtimestamp(start_ms / 1000, tz=self._timezone)

            # Local day management
            day_key = self._local_day_key(start_ms)
            hour = self._local_hour(start_ms)

            if last_day_key is None or day_key != last_day_key:
                run_kwh_from_midnight = 0.0
                last_day_key = day_key

            if day_key not in day_base_cache:
                # Priority 1: hour-to-hour continuity (prev entry was exactly 1h before)
                if (hour == 0
                        and prev_sum is not None
                        and prev_start is not None
                        and (start_ms - prev_start) == HOUR_MS):
                    day_base_cache[day_key] = prev_sum
                    # Capture this midnight in persistent store
                    mb[day_key] = round(prev_sum, 3)
                else:
                    # Fallback: persistent midnight_bases for this day
                    fallback = float(mb.get(day_key, 0.0))
                    if fallback > 0:
                        day_base_cache[day_key] = fallback
                    elif prev_sum is not None and prev_sum > 0:
                        day_base_cache[day_key] = prev_sum
                    else:
                        day_base_cache[day_key] = 0.0

                    # Persist fallback as the authoritative midnight base for this day
                    # so future partial reimports on this day window start correctly
                    if day_base_cache[day_key] > 0 and day_key not in mb:
                        mb[day_key] = round(day_base_cache[day_key], 3)

            # Hourly consumption Wh -> kWh
            kwh = wh / 1000.0
            run_kwh_from_midnight += kwh

            # Cumulative sum: priority = hour-to-hour continuity
            if (prev_sum is not None
                    and prev_start is not None
                    and (start_ms - prev_start) == HOUR_MS):
                cumul_sum = round(prev_sum + kwh, 3)
            else:
                # Fallback: day base + cumul since midnight
                cumul_sum = round(day_base_cache[day_key] + run_kwh_from_midnight, 3)

            stats.append(StatisticData(
                start=start_dt,
                state=cumul_sum,
                sum=cumul_sum,
            ))

            # Advance anchor for next point
            prev_sum = cumul_sum
            prev_start = start_ms

        if not stats:
            _LOGGER.debug("%s: no valid data points", statistic_id)
            return 0

        # --- Update persistent anchors ---
        last_stat = stats[-1]
        if "anchors" not in self._data:
            self._data["anchors"] = {}
        self._data["anchors"][statistic_id] = {
            "prev_sum": last_stat["sum"],
            "prev_start": int(last_stat["start"].timestamp() * 1000),
        }

        # --- Import (upsert) ---
        # async_import_statistics with source="recorder" does UPSERT on (metadata_id, start_ts).
        # No need to clear first: existing records at the same timestamps are updated in place.
        # Clearing before import caused "database is locked" errors because the recorder's
        # thread pool has multiple workers (DbWorker_0/1/2) - the DELETE and the pending
        # INSERTs from the previous room would race on the SQLite write lock.
        room = self._intuis_home.rooms.get(room_id)
        room_name = room.name if room else ("Room " + room_id)

        # mean_type + unit_class required from HA 2026.11 - try/except for backward compat
        try:
            from homeassistant.components.recorder.models import StatisticMeanType
            metadata = StatisticMetaData(
                mean_type=StatisticMeanType.NONE,
                has_sum=True,
                name=(room_name + " Energy"),
                source="recorder",
                statistic_id=statistic_id,
                unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
                unit_class="energy",
            )
        except (ImportError, TypeError):
            metadata = StatisticMetaData(
                has_mean=False,
                has_sum=True,
                name=(room_name + " Energy"),
                source="recorder",
                statistic_id=statistic_id,
                unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            )

        try:
            async_import_statistics(self._hass, metadata, stats)
            _LOGGER.info(
                "%s: imported %d hours [%s sum=%.3f -> %s sum=%.3f]",
                statistic_id, len(stats),
                stats[0]["start"].isoformat(), stats[0]["sum"],
                stats[-1]["start"].isoformat(), stats[-1]["sum"],
            )
            return len(stats)
        except Exception as err:
            _LOGGER.error("Import failed for %s: %s", statistic_id, err)
            return 0

    # -- Daily rebase (REMOVED) --------------------------------------------
    # midnight_bases is updated incrementally by _process_room at every
    # midnight boundary.  No separate daily rebase needed.

    # -- Initialize base from history import --------------------------------

    async def async_set_bases_from_import(
        self, midnight_sums: dict[str, dict[str, float]]
    ) -> None:
        """Populate midnight_bases after history_import finishes.

        Args:
            midnight_sums: {statistic_id: {
                "by_day": {day_key: float, ...},   # all midnight sums from import
                "sensor_base": float,  # today midnight (legacy key, optional)
                "base_kwh": float,     # J-1 midnight (legacy key, optional)
                "final_sum": float,
            }}
        """
        await self.load_storage()

        now_local = datetime.now(self._timezone)
        today_key = now_local.strftime("%Y-%m-%d")
        yesterday_key = (now_local - timedelta(days=1)).strftime("%Y-%m-%d")
        today_midnight = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        today_midnight_ms = int(today_midnight.astimezone(ZoneInfo("UTC")).timestamp() * 1000)

        mb_all = self._data.setdefault("midnight_bases", {})

        for statistic_id, sums in midnight_sums.items():
            mb = mb_all.setdefault(statistic_id, {})

            # Prefer new "by_day" dict (all midnights from import window)
            by_day = sums.get("by_day", {})
            if by_day:
                mb.update({k: round(v, 3) for k, v in by_day.items() if v})
            else:
                # Legacy keys (base_kwh = J-1 midnight, sensor_base = today midnight)
                base = sums.get("base_kwh")
                sb = sums.get("sensor_base")
                if base:
                    mb[yesterday_key] = round(base, 3)
                if sb:
                    mb[today_key] = round(sb, 3)

            # Anchor: set to today midnight so next cycle continues cleanly
            today_sb = mb.get(today_key, sums.get("sensor_base", 0.0) or sums.get("final_sum", 0.0))
            self._data.setdefault("anchors", {})[statistic_id] = {
                "prev_sum": round(float(today_sb), 3),
                "prev_start": today_midnight_ms,
            }

            _LOGGER.info(
                "Post-import %s: %d midnight bases loaded, anchor at today midnight=%.3f",
                statistic_id, len(mb), float(today_sb),
            )

        await self._save_storage()
        self._publish_sensor_base()
        _LOGGER.info("Post-import: midnight_bases set for %d sensors", len(midnight_sums))

    async def async_initialize_base_from_statistics(self) -> None:
        """Initialize midnight_bases from existing HA statistics.

        Scans backwards through midnights (today back to J-4) to populate
        midnight_bases[statistic_id][day_key] for all found midnights.
        This is called once when storage is empty (first run, or after
        storage was cleared).  After this, _process_room maintains
        midnight_bases incrementally.
        """
        from homeassistant.components.recorder.statistics import (
            statistics_during_period,
        )

        await self.load_storage()

        now = datetime.now(self._timezone)
        start_time = now - timedelta(days=200)
        today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Scan last 5 midnights (today back to J-4)
        midnights = []
        for days_ago in range(0, 5):
            m = today_midnight - timedelta(days=days_ago)
            label = ["today", "J-1", "J-2", "J-3", "J-4"][days_ago]
            midnights.append((label, m, m.strftime("%Y-%m-%d")))

        _LOGGER.info("Initializing midnight_bases from statistics")

        mb_all = self._data.setdefault("midnight_bases", {})

        for room_id in self._intuis_home.rooms:
            statistic_id = self._get_statistic_id(room_id)
            if not statistic_id:
                continue

            try:
                stats = await get_instance(self._hass).async_add_executor_job(
                    statistics_during_period,
                    self._hass,
                    start_time,
                    None,
                    {statistic_id},
                    "hour",
                    None,
                    {"sum"},
                )

                if statistic_id not in stats or not stats[statistic_id]:
                    _LOGGER.warning("No stats found for %s", statistic_id)
                    continue

                all_stats = stats[statistic_id]

                # Index sums by UTC timestamp
                sum_by_ts: dict[int, float] = {}
                last_sum = 0.0
                for s in all_stats:
                    s_start = s.get("start")
                    s_sum = s.get("sum", 0) or 0
                    if s_start is None:
                        continue
                    s_ts = s_start.timestamp() if hasattr(s_start, "timestamp") else float(s_start)
                    sum_by_ts[int(s_ts)] = float(s_sum)
                    last_sum = float(s_sum)

                mb = mb_all.setdefault(statistic_id, {})
                found_today = None

                for label, local_midnight, day_key in midnights:
                    midnight_utc_ts = int(local_midnight.astimezone(ZoneInfo("UTC")).timestamp())
                    # Stat ending AT midnight = stat starting 1h before midnight
                    stat_start_ts = midnight_utc_ts - HOUR_S
                    midnight_sum = sum_by_ts.get(stat_start_ts) or sum_by_ts.get(midnight_utc_ts)

                    if midnight_sum is None:
                        # Nearest prior stat fallback
                        for ts_k in sorted(sum_by_ts):
                            if ts_k <= stat_start_ts:
                                midnight_sum = sum_by_ts[ts_k]
                            else:
                                break

                    if midnight_sum is not None:
                        mb[day_key] = round(midnight_sum, 3)
                        _LOGGER.debug("Init %s: %s midnight=%.3f", statistic_id, label, midnight_sum)
                        if label == "today":
                            found_today = midnight_sum

                # Fallback anchor if today midnight not found
                anchor_base = found_today if found_today is not None else last_sum
                today_midnight_ms = int(today_midnight.astimezone(ZoneInfo("UTC")).timestamp() * 1000)
                self._data.setdefault("anchors", {})[statistic_id] = {
                    "prev_sum": round(anchor_base, 3),
                    "prev_start": today_midnight_ms,
                }

                _LOGGER.info("Init %s: %d midnight bases, anchor=%.3f",
                             statistic_id, len(mb), anchor_base)

            except Exception as err:
                _LOGGER.warning("Could not init %s: %s", statistic_id, err)

        await self._save_storage()
        self._publish_sensor_base()
        _LOGGER.info("Base initialization completed")

    # -- Lifecycle ---------------------------------------------------------

    async def async_start(self) -> None:
        if self._update_task is not None:
            _LOGGER.warning("Hourly stats updater already running")
            return
        self._stop_event.clear()
        self._update_task = asyncio.create_task(self._update_loop())
        _LOGGER.info("Hourly stats updater started (interval: %d min)", self._update_interval)

    async def async_stop(self) -> None:
        if self._update_task is None:
            return
        self._stop_event.set()
        self._update_task.cancel()
        try:
            await self._update_task
        except asyncio.CancelledError:
            pass
        self._update_task = None
        _LOGGER.info("Hourly stats updater stopped")

    async def _update_loop(self) -> None:
        # Initial delay to let HA stabilise
        await asyncio.sleep(60)

        while not self._stop_event.is_set():
            try:
                await self.async_update()
            except asyncio.CancelledError:
                raise
            except Exception as err:
                _LOGGER.error("Error in hourly stats loop: %s", err, exc_info=True)

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._update_interval * 60,
                )
                break
            except asyncio.TimeoutError:
                pass

    async def async_rebase_daily(self) -> None:
        """No-op: midnight_bases is maintained incrementally by _process_room."""
        _LOGGER.debug("async_rebase_daily: no-op (midnight_bases maintained incrementally)")
