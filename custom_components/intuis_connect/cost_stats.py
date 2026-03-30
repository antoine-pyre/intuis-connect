"""Energy cost statistics for Intuis Connect.

Calculates hourly energy cost (kWh × price) and writes cumulative cost
statistics to the HA recorder, mirroring the architecture of hourly_stats.py.

Price modes:
  - "fixed"  : constant price configured in options (€/kWh)
  - "entity" : HA entity whose state gives the current price (e.g. Octopus,
                Amber, or a template sensor from your electricity contract).
                Historical prices are retrieved from the recorder state history.

The cost sensor (sensor.X_cost) has state_class=TOTAL. Its native_value
the recorder does not generate competing statistics.  cost_stats is the sole
writer of statistics for these entities.

Cumulative algorithm:
  state = sum = running total of € since the beginning of time
  Each hour: sum[n] = sum[n-1] + hourly_kwh × price_at_that_hour
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import async_import_statistics
from homeassistant.helpers.storage import Store

from .utils.const import (
    DOMAIN,
    HISTORY_IMPORT_KEY,
    CONF_ENERGY_COST_ENABLED,
    CONF_ENERGY_PRICE_MODE,
    CONF_ENERGY_FIXED_PRICE,
    CONF_ENERGY_PRICE_ENTITY,
    DEFAULT_ENERGY_COST_ENABLED,
    DEFAULT_ENERGY_PRICE_MODE,
    DEFAULT_ENERGY_FIXED_PRICE,
    DEFAULT_ENERGY_PRICE_ENTITY,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from .entity.intuis_home import IntuisHome

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_KEY_PREFIX = "intuis_connect.cost_stats_v1_"

HOUR_MS = 3_600_000
MIDNIGHT_BASES_MAX_DAYS = 270



class CostStatsUpdater:
    """Calculates and imports hourly energy cost statistics.

    Must be called *after* HourlyStatsUpdater has determined the kWh values
    for the same time window.  Receives the raw hourly data (timestamp, wh)
    and the kWh stats already computed, then writes cost LTS.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        intuis_home: IntuisHome,
        entry_id: str,
        options: dict[str, Any],
        timezone_str: str = "Europe/Paris",
    ) -> None:
        self._hass = hass
        self._intuis_home = intuis_home
        self._entry_id = entry_id
        self._options = options
        self._timezone = ZoneInfo(timezone_str)
        self._timezone_str = timezone_str

        self._store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY_PREFIX}{entry_id}")
        self._data: dict[str, Any] = {}
        self._loaded = False
        self._update_lock = asyncio.Lock()

    # ------------------------------------------------------------------ #
    #  Configuration helpers                                               #
    # ------------------------------------------------------------------ #

    def _is_enabled(self) -> bool:
        return self._options.get(CONF_ENERGY_COST_ENABLED, DEFAULT_ENERGY_COST_ENABLED)

    def _price_mode(self) -> str:
        return self._options.get(CONF_ENERGY_PRICE_MODE, DEFAULT_ENERGY_PRICE_MODE)

    def _fixed_price(self) -> float:
        return float(self._options.get(CONF_ENERGY_FIXED_PRICE, DEFAULT_ENERGY_FIXED_PRICE))

    def _price_entity(self) -> str:
        return self._options.get(CONF_ENERGY_PRICE_ENTITY, DEFAULT_ENERGY_PRICE_ENTITY) or ""

    def update_options(self, options: dict[str, Any]) -> None:
        """Called when options are updated (entry reload)."""
        self._options = options

    # ------------------------------------------------------------------ #
    #  Storage                                                             #
    # ------------------------------------------------------------------ #

    async def load_storage(self) -> None:
        if self._loaded:
            return
        stored = await self._store.async_load()
        if stored:
            self._data = stored
        else:
            self._data = {
                "midnight_bases": {},  # {statistic_id: {day_key: float}}
                "anchors": {},         # {statistic_id: {"prev_sum": float, "prev_start": int ms}}
            }
        self._loaded = True

    async def _save_storage(self) -> None:
        cutoff = (datetime.now(self._timezone) - timedelta(days=MIDNIGHT_BASES_MAX_DAYS)).strftime("%Y-%m-%d")
        mb = self._data.get("midnight_bases", {})
        for sid in mb:
            mb[sid] = {k: v for k, v in mb[sid].items() if k >= cutoff}
        await self._store.async_save(self._data)

    # ------------------------------------------------------------------ #
    #  Entity helpers                                                      #
    # ------------------------------------------------------------------ #

    def _get_cost_statistic_id(self, room_id: str) -> str | None:
        """Return the cost sensor entity_id for a room.

        Also warns if the entity got a '_2' suffix (entity registry conflict),
        which means there is an orphaned old entity that should be deleted from
        Settings > Entities so the integration can reclaim the clean entity_id.
        """
        from homeassistant.helpers import entity_registry as er

        unique_id = f"intuis_{self._intuis_home.id}_{room_id}_cost"
        ent_reg = er.async_get(self._hass)
        entity_id = ent_reg.async_get_entity_id("sensor", DOMAIN, unique_id)

        if not entity_id:
            room = self._intuis_home.rooms.get(room_id)
            _LOGGER.warning(
                "Cost entity not found: unique_id=%s, room=%s",
                unique_id,
                room.name if room else room_id,
            )
            return None

        if entity_id.endswith("_2") or "_2" in entity_id.split(".")[-1].split("_")[-1:]:
            _LOGGER.warning(
                "Cost sensor has conflicting entity_id '%s' (expected without '_2'). "
                "An orphaned entity is occupying the clean entity_id. "
                "Fix: Settings > Entities > search '_cost' > delete the orphan > reload integration.",
                entity_id,
            )

        return entity_id

    # ------------------------------------------------------------------ #
    #  Price resolution                                                    #
    # ------------------------------------------------------------------ #

    def _get_current_price(self) -> float | None:
        """Return the current price per kWh."""
        if self._price_mode() == "fixed":
            return self._fixed_price()

        entity_id = self._price_entity()
        if not entity_id:
            return None
        state = self._hass.states.get(entity_id)
        if state is None or state.state in ("unavailable", "unknown", ""):
            _LOGGER.warning("Price entity %s unavailable", entity_id)
            return None
        try:
            return float(state.state)
        except ValueError:
            _LOGGER.warning("Price entity %s has non-numeric state: %s", entity_id, state.state)
            return None

    async def _get_price_history(
        self, start_dt: datetime, end_dt: datetime
    ) -> list[tuple[datetime, float]]:
        """Return [(datetime, price)] for the entity price history window.

        Falls back to current state if no history is available.
        Sorted chronologically.
        """
        if self._price_mode() == "fixed":
            price = self._fixed_price()
            return [(start_dt, price)]

        entity_id = self._price_entity()
        if not entity_id:
            return []

        try:
            from homeassistant.components.recorder.history import (
                get_significant_states,
            )

            def _fetch() -> list:
                return get_significant_states(
                    self._hass,
                    start_dt,
                    end_dt,
                    entity_ids=[entity_id],
                    significant_changes_only=False,
                )

            history = await get_instance(self._hass).async_add_executor_job(_fetch)
            states = history.get(entity_id, [])
            result: list[tuple[datetime, float]] = []
            for s in states:
                try:
                    price = float(s.state)
                    lc = s.last_changed
                    # last_changed may be float (epoch) in some HA versions
                    if isinstance(lc, float):
                        lc = datetime.fromtimestamp(lc, tz=ZoneInfo("UTC"))
                    elif lc is not None and not lc.tzinfo:
                        lc = lc.replace(tzinfo=ZoneInfo("UTC"))
                    if lc is not None:
                        result.append((lc, price))
                except (ValueError, AttributeError):
                    pass
            if result:
                return result
        except Exception as err:
            _LOGGER.debug("Could not fetch price history for %s: %s", entity_id, err)

        # Fallback: current state for entire window
        current = self._get_current_price()
        if current is not None:
            return [(start_dt, current)]
        return []

    @staticmethod
    def _price_at(price_history: list[tuple[datetime, float]], dt: datetime) -> float | None:
        """Return the price active at *dt* from a sorted price history list."""
        if not price_history:
            return None
        result = price_history[0][1]
        for ts, price in price_history:
            if ts <= dt:
                result = price
            else:
                break
        return result

    def publish_cost_base(self) -> None:
        """Publish latest imported cumulative cost sum to hass.data[DOMAIN]['cost_base'].

        Critical invariant: the published value MUST NEVER DECREASE.

        With state_class=TOTAL, HA's recorder tracks entity state deltas and
        compiles them into short-term and then hourly LTS. If the entity state
        drops (e.g. because a fresh recompute from mb[day_key] yields a lower
        cumulative than the previous anchor), HA records a negative delta in
        short-term stats, which then corrupts the hourly LTS and produces
        negative costs in the Energy Dashboard.

        Root cause: mb[day_key] set by recalculate can be slightly lower than
        the value the subsequent hourly imports computed, because recalculate
        ran when the API only had partial data. The next hourly import rebuilds
        the cumulative chain from mb[day_key] and produces a lower endpoint.

        Fix: take max(new_import_value, last_published_value). This ensures the
        entity state only ever increases. HA's short-term compilation always
        sees non-negative deltas. The LTS is still corrected by our UPSERT.
        """
        if DOMAIN not in self._hass.data:
            self._hass.data[DOMAIN] = {}

        existing_base = self._hass.data.get(DOMAIN, {}).get("cost_base", {})
        anchors = self._data.get("anchors", {})
        cost_base: dict[str, float] = {}
        for sid, anchor_data in anchors.items():
            new_val = anchor_data.get("prev_sum")
            if new_val is not None:
                new_val = float(new_val)
                old_val = float(existing_base.get(sid, 0.0))
                # Never let the entity state decrease — monotonically non-decreasing
                cost_base[sid] = max(new_val, old_val)

        self._hass.data[DOMAIN]["cost_base"] = cost_base

    async def _init_midnight_bases_from_lts(self) -> None:
        """Populate midnight_bases from existing cost LTS data.

        Called when midnight_bases is empty (fresh install, storage cleared,
        or crash).  Reads the last two days of cost statistics from the
        recorder for each room and extracts the sum at midnight local time.
        """
        from homeassistant.components.recorder import get_instance
        from homeassistant.components.recorder.statistics import statistics_during_period

        now_local = datetime.now(self._timezone)
        start_utc = (now_local - timedelta(days=3)).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).astimezone(ZoneInfo("UTC"))
        end_utc = now_local.astimezone(ZoneInfo("UTC"))

        mb_all = self._data.setdefault("midnight_bases", {})
        found = 0

        for room_id in self._intuis_home.rooms:
            sid = self._get_cost_statistic_id(room_id)
            if not sid:
                continue
            try:
                stats = await get_instance(self._hass).async_add_executor_job(
                    statistics_during_period,
                    self._hass,
                    start_utc,
                    end_utc,
                    {sid},
                    "hour",
                    None,
                    {"sum"},
                )
            except Exception as err:
                _LOGGER.debug("Could not init mb from LTS for %s: %s", sid, err)
                continue

            rows = stats.get(sid, [])
            if not rows:
                continue

            mb = mb_all.setdefault(sid, {})
            prev_sum: float | None = None
            for row in rows:
                raw = row.get("start")
                s = row.get("sum")
                if raw is None or s is None:
                    continue
                if isinstance(raw, float):
                    dt = datetime.fromtimestamp(raw, tz=ZoneInfo("UTC"))
                elif hasattr(raw, "tzinfo"):
                    dt = raw if raw.tzinfo else raw.replace(tzinfo=ZoneInfo("UTC"))
                else:
                    continue
                dt_local = dt.astimezone(self._timezone)
                if dt_local.hour == 0 and prev_sum is not None:
                    # The sum at midnight is the cumulative at end of the slot
                    # just before midnight = prev_sum.
                    day_key = dt_local.strftime("%Y-%m-%d")
                    mb[day_key] = round(float(prev_sum), 4)
                    found += 1
                prev_sum = float(s)

        if found:
            _LOGGER.info("CostStats: initialized %d midnight_bases from LTS", found)
            await self._save_storage()

    # ------------------------------------------------------------------ #
    #  Main update                                                         #
    # ------------------------------------------------------------------ #

    async def async_update(
        self,
        room_hourly_data: dict[str, list[tuple[int, float]]],
    ) -> int:
        """Compute and import cost stats for all rooms.

        Args:
            room_hourly_data: {room_id: [(timestamp_sec, wh), ...]}
                              Same data already used by HourlyStatsUpdater.
        Returns:
            Total number of cost stat points written.
        """
        if not self._is_enabled():
            return 0

        if self._update_lock.locked():
            return 0

        async with self._update_lock:
            await self.load_storage()

            # Auto-initialize midnight_bases from existing cost LTS if empty.
            # This recovers from storage corruption, fresh installs, or crashes
            # by reading the last known cumulative cost at midnight from the DB.
            mb_all = self._data.get("midnight_bases", {})
            if not mb_all or all(not v for v in mb_all.values()):
                await self._init_midnight_bases_from_lts()

            # Determine time window for price history fetch
            now_local = datetime.now(self._timezone)
            today_midnight = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
            yesterday_midnight = today_midnight - timedelta(days=1)
            start_dt = yesterday_midnight.astimezone(ZoneInfo("UTC"))
            end_dt = now_local.astimezone(ZoneInfo("UTC"))

            price_history = await self._get_price_history(start_dt, end_dt)
            if not price_history:
                _LOGGER.warning("No price data available — skipping cost stats")
                return 0

            total = 0
            for room_id, hourly_data in room_hourly_data.items():
                if not hourly_data:
                    continue
                try:
                    total += await self._process_room(room_id, hourly_data, price_history)
                except Exception as err:
                    _LOGGER.warning("Cost stats error for room %s: %s", room_id, err)

            await self._save_storage()
            return total

    # ------------------------------------------------------------------ #
    #  Per-room processing                                                 #
    # ------------------------------------------------------------------ #

    async def _process_room(
        self,
        room_id: str,
        hourly_data: list[tuple[int, float]],
        price_history: list[tuple[datetime, float]],
    ) -> int:
        statistic_id = self._get_cost_statistic_id(room_id)
        if not statistic_id:
            return 0

        anchors = self._data.get("anchors", {}).get(statistic_id, {})
        prev_sum = anchors.get("prev_sum")
        prev_start = anchors.get("prev_start")

        mb_all = self._data.setdefault("midnight_bases", {})
        mb = mb_all.setdefault(statistic_id, {})

        if prev_sum is not None:
            prev_sum = float(prev_sum)
        if prev_start is not None:
            prev_start = int(prev_start)

        run_cost_from_midnight = 0.0
        last_day_key = None
        day_base_cache: dict[str, float] = {}
        stats = []

        for timestamp_sec, wh in hourly_data:
            if wh is None or not isinstance(wh, (int, float)) or wh != wh:
                continue
            if wh < 0:
                continue

            start_ms = (int(timestamp_sec * 1000) // HOUR_MS) * HOUR_MS
            start_dt = datetime.fromtimestamp(start_ms / 1000, tz=self._timezone)
            start_dt_utc = start_dt.astimezone(ZoneInfo("UTC"))

            kwh = wh / 1000.0
            price = self._price_at(price_history, start_dt_utc)
            if price is None:
                price = self._fixed_price()

            cost = round(kwh * price, 4)

            day_key = start_dt.strftime("%Y-%m-%d")
            hour = start_dt.hour

            if last_day_key is None or day_key != last_day_key:
                run_cost_from_midnight = 0.0
                last_day_key = day_key

            if day_key not in day_base_cache:
                if (
                    hour == 0
                    and prev_sum is not None
                    and prev_start is not None
                    and (start_ms - prev_start) == HOUR_MS
                ):
                    day_base_cache[day_key] = prev_sum
                    mb[day_key] = round(prev_sum, 4)
                else:
                    fallback = float(mb.get(day_key, 0.0))
                    if fallback > 0:
                        day_base_cache[day_key] = fallback
                    elif prev_sum is not None and prev_sum > 0:
                        # Use prev_sum as best-effort base for computation,
                        # but NEVER persist it to mb: prev_sum may be from a
                        # different day's anchor and would corrupt midnight_bases.
                        # mb[day_key] is only written via the consecutive hour==0
                        # path above, which has guaranteed chain integrity.
                        day_base_cache[day_key] = prev_sum
                    else:
                        day_base_cache[day_key] = 0.0
                    # Do NOT write mb[day_key] here: the fallback value
                    # (especially prev_sum) cannot be trusted as a midnight base.

            run_cost_from_midnight += cost

            if (
                prev_sum is not None
                and prev_start is not None
                and (start_ms - prev_start) == HOUR_MS
            ):
                cumul_sum = round(prev_sum + cost, 4)
            else:
                cumul_sum = round(day_base_cache[day_key] + run_cost_from_midnight, 4)

            stats.append(StatisticData(
                start=start_dt,
                state=cumul_sum,
                sum=cumul_sum,
            ))

            prev_sum = cumul_sum
            prev_start = start_ms

        if not stats:
            return 0

        # Persist anchor
        last_stat = stats[-1]
        self._data.setdefault("anchors", {})[statistic_id] = {
            "prev_sum": last_stat["sum"],
            "prev_start": int(last_stat["start"].timestamp() * 1000),
        }

        # Import
        room = self._intuis_home.rooms.get(room_id)
        room_name = room.name if room else ("Room " + room_id)
        currency = self._hass.config.currency or "EUR"

        try:
            from homeassistant.components.recorder.models import StatisticMeanType
            metadata = StatisticMetaData(
                mean_type=StatisticMeanType.NONE,
                has_sum=True,
                name=(room_name + " Cost"),
                source="recorder",
                statistic_id=statistic_id,
                unit_of_measurement=currency,
                unit_class=None,
            )
        except (ImportError, TypeError):
            metadata = StatisticMetaData(
                has_mean=False,
                has_sum=True,
                name=(room_name + " Cost"),
                source="recorder",
                statistic_id=statistic_id,
                unit_of_measurement=currency,
                unit_class=None,
            )

        try:
            async_import_statistics(self._hass, metadata, stats)
            _LOGGER.info(
                "%s: cost imported %d hours [%.4f -> %.4f %s]",
                statistic_id, len(stats),
                stats[0]["sum"], stats[-1]["sum"], currency,
            )
            return len(stats)
        except Exception as err:
            _LOGGER.error("Cost import failed for %s: %s", statistic_id, err)
            return 0

    # ------------------------------------------------------------------ #
    #  History recalculation                                               #
    # ------------------------------------------------------------------ #

    async def async_recalculate_history(
        self,
        days: int = 365,
        room_id_filter: str | None = None,
    ) -> int:
        """Recalculate cost statistics from existing energy statistics.

        Reads energy LTS from HA recorder, fetches price history for the
        whole window, and rewrites cost LTS.

        Args:
            days: How many days of history to recalculate.
            room_id_filter: Limit recalculation to a specific room_id.
        Returns:
            Total cost stat points written.
        """
        if not self._is_enabled():
            _LOGGER.warning("Cost stats disabled — nothing to recalculate")
            return 0

        await self.load_storage()

        now_local = datetime.now(self._timezone)
        start_local = now_local - timedelta(days=days)
        start_utc = start_local.astimezone(ZoneInfo("UTC"))
        end_utc = now_local.astimezone(ZoneInfo("UTC"))

        # Fetch price history for the full window
        price_history = await self._get_price_history(start_utc, end_utc)
        if not price_history:
            _LOGGER.error("No price data — cannot recalculate cost history")
            return 0

        from homeassistant.components.recorder.statistics import statistics_during_period

        total = 0
        rooms_to_process = (
            {room_id_filter: self._intuis_home.rooms.get(room_id_filter)}
            if room_id_filter
            else self._intuis_home.rooms
        )

        for room_id, room in rooms_to_process.items():
            if room is None:
                continue

            # Find the energy statistic_id for this room
            from homeassistant.helpers import entity_registry as er
            unique_id = f"intuis_{self._intuis_home.id}_{room_id}_energy"
            ent_reg = er.async_get(self._hass)
            energy_sid = ent_reg.async_get_entity_id("sensor", DOMAIN, unique_id)
            if not energy_sid:
                _LOGGER.warning("No energy sensor for room %s — skipping cost recalculation", room_id)
                continue

            cost_sid = self._get_cost_statistic_id(room_id)
            if not cost_sid:
                continue

            _LOGGER.info("Recalculating cost history for %s (%d days)", room_id, days)

            try:
                stats = await get_instance(self._hass).async_add_executor_job(
                    statistics_during_period,
                    self._hass,
                    start_utc,
                    end_utc,
                    {energy_sid},
                    "hour",
                    None,
                    {"sum", "state"},
                )
            except Exception as err:
                _LOGGER.warning("Could not read energy stats for %s: %s", room_id, err)
                continue

            energy_stats = stats.get(energy_sid, [])
            if not energy_stats:
                _LOGGER.info("No energy stats found for %s", room_id)
                continue

            # Build hour→kWh from stat diffs (state increases)
            # sum[n] - sum[n-1] = kWh for hour n
            cost_stats: list[StatisticData] = []
            prev_energy_sum: float | None = None
            cumul_cost = 0.0

            # Initialise from existing cost anchor if available
            # (so we don't reset to 0 mid-history when recalculating a subset)
            # For full recalculation we reset to 0.
            if days >= 365:
                # Full recalc: start from 0
                cost_anchor_sum = 0.0
            else:
                # Partial recalc: try to start from last known cost before window
                cost_anchor_sum = 0.0
                existing_anchors = self._data.get("anchors", {}).get(cost_sid, {})
                # We can't easily get the cost at start_utc without querying LTS again.
                # For simplicity, reset for partial recalc too.
                # A future improvement: query cost LTS at start_utc.

            cumul_cost = cost_anchor_sum

            mb_all = self._data.setdefault("midnight_bases", {})
            mb = mb_all.setdefault(cost_sid, {})
            mb.clear()  # Reset midnight bases for full recalculation

            for stat in energy_stats:
                s_start_raw = stat.get("start")
                s_sum = stat.get("sum")
                if s_start_raw is None or s_sum is None:
                    continue
                s_sum = float(s_sum)

                # statistics_during_period may return start as:
                #   - float  (Unix timestamp) in recent HA versions
                #   - datetime object in older HA versions
                if isinstance(s_start_raw, float):
                    s_start_aware = datetime.fromtimestamp(s_start_raw, tz=ZoneInfo("UTC"))
                elif isinstance(s_start_raw, (int,)):
                    s_start_aware = datetime.fromtimestamp(float(s_start_raw), tz=ZoneInfo("UTC"))
                elif hasattr(s_start_raw, "tzinfo"):
                    s_start_aware = (
                        s_start_raw if s_start_raw.tzinfo
                        else s_start_raw.replace(tzinfo=ZoneInfo("UTC"))
                    )
                else:
                    _LOGGER.warning("Unexpected start type %s: %s", type(s_start_raw), s_start_raw)
                    continue

                if prev_energy_sum is None:
                    prev_energy_sum = s_sum
                    continue  # can't compute diff for first point

                kwh_this_hour = max(0.0, s_sum - prev_energy_sum)
                prev_energy_sum = s_sum

                # Get price at this hour
                price = self._price_at(price_history, s_start_aware)
                if price is None:
                    price = self._fixed_price()

                cost_this_hour = round(kwh_this_hour * price, 4)
                cumul_cost = round(cumul_cost + cost_this_hour, 4)

                # Track midnight bases.
                # Key convention MUST match _process_room: day_key = local day
                # of the data point (start_dt.strftime("%Y-%m-%d")).
                # For the midnight slot (hour==0), the local day IS the day
                # this slot belongs to, so key = s_local.strftime("%Y-%m-%d").
                # The base for that day = cumul_cost BEFORE this hour's cost
                # = cost at the start of this midnight hour = cost at end of
                # the previous day = correct base for all of s_local.date().
                s_local = s_start_aware.astimezone(self._timezone)
                if s_local.hour == 0:
                    day_key = s_local.strftime("%Y-%m-%d")
                    mb[day_key] = round(cumul_cost - cost_this_hour, 4)

                cost_stats.append(StatisticData(
                    start=s_start_aware,
                    state=cumul_cost,
                    sum=cumul_cost,
                ))

            if not cost_stats:
                _LOGGER.info("No cost stats produced for %s", room_id)
                continue

            # Import cost stats
            room_name = room.name if room else room_id
            currency = self._hass.config.currency or "EUR"

            try:
                from homeassistant.components.recorder.models import StatisticMeanType
                metadata = StatisticMetaData(
                    mean_type=StatisticMeanType.NONE,
                    has_sum=True,
                    name=(room_name + " Cost"),
                    source="recorder",
                    statistic_id=cost_sid,
                    unit_of_measurement=currency,
                    unit_class=None,
                )
            except (ImportError, TypeError):
                metadata = StatisticMetaData(
                    has_mean=False,
                    has_sum=True,
                    name=(room_name + " Cost"),
                    source="recorder",
                    statistic_id=cost_sid,
                    unit_of_measurement=currency,
                    unit_class=None,
                )

            try:
                async_import_statistics(self._hass, metadata, cost_stats)
                # Update anchor
                last = cost_stats[-1]
                self._data.setdefault("anchors", {})[cost_sid] = {
                    "prev_sum": last["sum"],
                    "prev_start": int(last["start"].timestamp() * 1000),
                }
                total += len(cost_stats)
                _LOGGER.info(
                    "Recalculated cost history for %s: %d points, total=%.4f %s",
                    room_id, len(cost_stats), last["sum"], currency,
                )
            except Exception as err:
                _LOGGER.error("Cost history import failed for %s: %s", room_id, err)

        await self._save_storage()
        return total

    # ------------------------------------------------------------------ #
    #  Post-history-import hook                                            #
    # ------------------------------------------------------------------ #

    async def async_set_bases_from_import(
        self, midnight_sums_cost: dict[str, dict[str, float]]
    ) -> None:
        """Populate midnight_bases from a history import that also computed cost."""
        await self.load_storage()
        mb_all = self._data.setdefault("midnight_bases", {})
        for cost_sid, by_day in midnight_sums_cost.items():
            mb = mb_all.setdefault(cost_sid, {})
            mb.update({k: round(v, 4) for k, v in by_day.items() if v})
        await self._save_storage()
