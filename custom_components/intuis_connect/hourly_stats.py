"""Hourly external energy statistics: manual import and opt-in updater.

Adapted from TheFab21's hourly import/updater proposals (#17, #22, #24):
https://github.com/antoine-pyre/intuis-connect/pull/22
Rooms and the home total are distinct external series; daily sensors are untouched.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from homeassistant.components.recorder import get_instance, statistics
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_call_later, async_track_time_interval

from .cost_stats import (
    CostPriceError,
    async_hour_prices,
    async_publish_costs,
    async_write_costs,
    cost_metadata,
    hourly_costs,
)
from .energy_base import (
    EnergyBase,
    daily_totals,
    local_midnight,
    settled_day,
)
from .external_statistics import metadata, statistic_id
from .hourly_series import (
    HOUR,
    closed_hour_end,
    energy_rooms,
    home_total_status,
    hourly_windows,
    stage_hourly,
    sum_hourly,
)
from .intuis_api.api import (
    APIError,
    CannotConnect,
    EnergyDataUnavailable,
    InvalidAuth,
    NoRoomMeasureDevice,
    RateLimitError,
)
from .recorder_import import HistoryReplacementError, async_replace_external_history
from .utils.const import CONF_COST_STATISTICS, DOMAIN

if TYPE_CHECKING:
    from .entity.intuis_home import IntuisHome
    from .history_import import HistoryImportManager
    from .intuis_api.api import IntuisAPI

_LOGGER = logging.getLogger(__name__)
UPDATE_WINDOW = 48 * HOUR
CATCH_UP_WINDOW = 7 * 24 * HOUR
FIRST_UPDATE_DELAY = 60  # seconds; lets the recorder and first refresh settle
# How far back a seed looks for the series' own value at a day boundary.
SEED_LOOKBACK_DAYS = 30


def room_metadata(home_id: str, room_id: str, room_name: str) -> dict[str, Any]:
    return metadata(home_id, room_id, f"{room_name} hourly energy")


def home_metadata(home_id: str, home_name: str) -> dict[str, Any]:
    return metadata(home_id, None, f"{home_name} hourly energy")


async def async_last_hour(hass: HomeAssistant, sid: str) -> int | None:
    """Last confirmed hour, read from the recorder rather than auxiliary storage."""
    rows = await get_instance(hass).async_add_executor_job(
        statistics.get_last_statistics, hass, 1, sid, False, {"sum"}
    )
    if not rows.get(sid):
        return None
    start = rows[sid][0]["start"]
    return int(start.timestamp() if isinstance(start, datetime) else start)


async def async_sum_at(hass: HomeAssistant, sid: str, boundary: datetime) -> float:
    """Cumulative sum of the last hour that ends at or before ``boundary``.

    Seeding the level needs the series' own value at a day boundary, not its
    latest value: taking the latest would count the hours after the boundary
    twice once they are rewritten against the level.
    """
    rows = await get_instance(hass).async_add_executor_job(
        statistics.statistics_during_period,
        hass,
        boundary - timedelta(days=SEED_LOOKBACK_DAYS),
        boundary,
        {sid},
        "hour",
        None,
        {"sum"},
    )
    series = rows.get(sid) or []
    for row in reversed(series):
        value = row.get("sum")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return 0.0


async def async_update_window(
    hass: HomeAssistant, home_id: str, room_ids: list[str], now: datetime
) -> tuple[int, int]:
    """Re-read 48 closed hours, and resume up to 7 days after an interruption."""
    end = closed_hour_end(now)
    start = end - UPDATE_WINDOW
    for room_id in room_ids:
        last = await async_last_hour(hass, statistic_id(home_id, room_id))
        if last is not None:
            start = min(start, last + HOUR)
    return max(start, end - CATCH_UP_WINDOW), end


async def async_rebase_levels(
    hass: HomeAssistant,
    api: IntuisAPI,
    intuis_home: IntuisHome,
    manager: HistoryImportManager,
    zone: ZoneInfo,
    now: datetime,
) -> dict[str, Any]:
    """Advance the absolute level from the cloud's consolidated daily measure.

    Adapted from TheFab21's Node-RED flow: the hourly series alone carries an
    error forward for good, so a once-a-day pass re-anchors it on the 1day
    value of a settled local day. Idempotent by the stored settled day; the
    level is committed only once every room answered, since a partial advance
    would understate the rooms it skipped.
    """
    from .history_import import API_DELAY_SECONDS

    base = EnergyBase(manager._state)
    rooms = energy_rooms(intuis_home)
    home_id = intuis_home.id
    if not rooms:
        _LOGGER.debug("Energy rebase: no rooms with equipment")
        return {"rebase": "no rooms"}
    if base.needs_reseed(now, zone):
        through = settled_day(now, zone)
        boundary = local_midnight(through + timedelta(days=1), zone)
        levels = {
            room_id: await async_sum_at(hass, statistic_id(home_id, room_id), boundary)
            for room_id, _ in rooms
        }
        base.seed(through, levels)
        await manager.async_save()
        _LOGGER.debug("Energy level seeded through %s: %s", through, levels)
        return {"rebase": "seeded", "through": through.isoformat()}
    plan = base.plan(now, zone)
    if plan is None:
        # Logged too: silence here was mistaken for the rebase never running.
        _LOGGER.debug(
            "Energy rebase up to date, level settled through %s", base.settled_through
        )
        return {"rebase": "up to date"}
    bulk = None
    paired = bridged_rooms(hass, manager.entry_id, intuis_home, rooms)
    try:
        if paired and api.home_measure_supported:
            bulk = await api.async_get_home_energy_daily(
                paired, plan.begin, plan.end
            )
    except RateLimitError as err:
        # Falling back would issue one request per room, the opposite of what
        # a rate limit asks for.
        _LOGGER.warning("Energy rebase postponed, rate limited: %s", err)
        return {"rebase": "postponed", "error": str(err)}
    except (APIError, CannotConnect, InvalidAuth, ValueError, OSError) as err:
        _LOGGER.info("Home daily measure unavailable, asking room by room: %s", err)
        bulk = None
    added: dict[str, float] = {}
    for room_id, room_name in rooms:
        try:
            if bulk is None:
                samples = await api.async_get_room_energy_daily(
                    room_id, plan.begin, plan.end - 1
                )
            else:
                samples = bulk.get(room_id, [])
            totals = daily_totals(samples, zone, plan.first, plan.last)
        except EnergyDataUnavailable:
            # Settled days the cloud never measured add nothing, like the flow.
            totals = {}
        except (APIError, CannotConnect, InvalidAuth, ValueError, OSError) as err:
            # Nothing is committed: the whole catch-up is retried next cycle.
            _LOGGER.warning("Energy rebase postponed for %s: %s", room_name, err)
            return {"rebase": "postponed", "error": f"{room_name}: {err}"}
        if len(totals) < plan.days:
            _LOGGER.info(
                "%s: %d of %d settled days had no measurement",
                room_name,
                plan.days - len(totals),
                plan.days,
            )
        added[room_id] = sum(totals.values())
        if bulk is None:
            await asyncio.sleep(API_DELAY_SECONDS)
    base.advance(plan.last, added)
    await manager.async_save()
    _LOGGER.debug("Energy level advanced through %s: %s", plan.last, added)
    return {
        "rebase": "advanced",
        "through": plan.last.isoformat(),
        "days": plan.days,
        "added_kwh": round(sum(added.values()), 3),
    }


def home_bridge(hass: HomeAssistant, entry_id: str, intuis_home: IntuisHome) -> str:
    """The gateway the home reports through, empty when none is known.

    The home object a cycle holds was built at setup and carries no bridge;
    only the coordinator's refreshed modules do, which is where the gateway
    sensors read theirs. The flow this mirrors sends one gateway for every
    room, so the first one found serves them all.
    """
    data = (hass.data.get(DOMAIN, {}).get(entry_id, {}) or {}).get("coordinator")
    for module in (getattr(data, "data", None) or {}).get("modules", ()) or ():
        if bridge := getattr(module, "bridge", "") or "":
            return bridge
    rooms = getattr(intuis_home, "rooms", None) or {}
    for room in rooms.values():
        if bridge := getattr(room, "bridge_id", "") or "":
            return bridge
    for room in rooms.values():
        for module in getattr(room, "modules", None) or ():
            if bridge := getattr(module, "bridge", "") or "":
                return bridge
    return ""


def bridged_rooms(
    hass: HomeAssistant, entry_id: str, intuis_home: IntuisHome, rooms
) -> list[tuple[str, str]]:
    """(room_id, bridge) pairs the home endpoint needs for one bulk request.

    Empty when no gateway is known: the endpoint answers 404 to a room whose
    bridge is blank, so asking would only cost a failed request.
    """
    fallback = home_bridge(hass, entry_id, intuis_home)
    paired = [
        (
            room_id,
            (getattr(rooms_of(intuis_home).get(room_id), "bridge_id", "") or "")
            or fallback,
        )
        for room_id, _ in rooms
    ]
    return paired if all(bridge for _, bridge in paired) else []


def rooms_of(intuis_home: IntuisHome) -> dict:
    """Rooms of a home, tolerating one that carries none."""
    return getattr(intuis_home, "rooms", None) or {}


def entry_cost_options(options: Any) -> dict[str, Any] | None:
    """Cost settings of one entry, only when that entry enabled costs."""
    return dict(options) if options.get(CONF_COST_STATISTICS) else None


async def async_import_hourly_history(
    hass: HomeAssistant,
    api: IntuisAPI,
    intuis_home: IntuisHome,
    manager: HistoryImportManager,
    *,
    start: int,
    end: int,
    room_filter: str | None = None,
    home_id: str | None = None,
    cost_options: dict[str, Any] | None = None,
    baselines: dict[str, float] | None = None,
) -> dict:
    """Fetch, stage, then replace one external series transaction per room.

    Only confirmed hours are written; an hour the cloud has not measured yet
    keeps its statistics and is filled by a later run. The home total is the
    sum over hours every room confirmed, and is not written when a room failed.
    With cost options, each confirmed room also gets its cost series from the
    same confirmed kWh; a price problem never blocks or alters the energy.
    """
    from .history_import import API_DELAY_SECONDS

    if manager._running or manager._closing:
        return {"error": "Import already running or entry unloading"}
    manager._running = True
    manager._task = asyncio.current_task()
    manager._cancelled = False
    manager.status = "importing"
    manager.last_error = None
    manager.rooms_completed = manager.total_rooms = 0
    manager.days_imported = manager.total_days = 0
    results: dict[str, Any] = {
        "rooms_imported": 0,
        "total_energy_kwh": 0.0,
        "errors": [],
        "home_total": "skipped",
        "costs": "disabled",
        "cost_errors": [],
    }
    cost_errors: list[str] = results["cost_errors"]
    costed: dict[str, tuple[tuple[datetime, float], ...]] = {}
    try:
        home_id = home_id or intuis_home.id
        rooms = energy_rooms(intuis_home, room_filter)
        manager.total_rooms = len(rooms)
        manager.total_days = (end - start) // 86400
        if not rooms:
            results["errors"].append("No matching rooms")
        confirmed: dict[str, tuple[tuple[datetime, float], ...]] = {}
        # Rooms the cloud cannot measure: skipped, and not missing from totals.
        unmeasured: set[str] = set()
        currency = hass.config.currency
        prices = None
        if cost_options and rooms:
            try:
                hours = range(start, end, HOUR)
                prices = dict(
                    zip(
                        hours,
                        await async_hour_prices(hass, cost_options, currency, hours),
                    )
                )
            except Exception as err:  # noqa: BLE001 - costs never block energy
                cost_errors.append(f"Costs: {err}")
        bulk: dict[str, list[tuple[int, float]]] | None = None
        paired = bridged_rooms(hass, manager.entry_id, intuis_home, rooms)
        if paired and api.home_measure_supported:
            try:
                bulk = await api.async_get_home_energy_hourly(paired, start, end)
            except RateLimitError:
                # One request per room is the opposite of what a 429 asks for.
                raise
            except (APIError, CannotConnect, InvalidAuth, ValueError, OSError) as err:
                _LOGGER.info(
                    "Home hourly measure unavailable, asking room by room: %s", err
                )
        for room_id, room_name in rooms:
            if manager._cancelled:
                raise asyncio.CancelledError
            manager.current_room = room_name
            try:
                values = (
                    bulk.get(room_id, [])
                    if bulk is not None
                    else await api.async_get_room_energy_hourly(room_id, start, end)
                )
                samples = stage_hourly(values, start, end)
                if manager._cancelled:
                    raise asyncio.CancelledError
                committed = await async_replace_external_history(
                    hass,
                    room_metadata(home_id, room_id, room_name),
                    hourly_windows(samples),
                    baselines.get(room_id) if baselines else None,
                )
                confirmed[room_id] = samples
                results["rooms_imported"] += 1
                results["total_energy_kwh"] += committed.total
                manager.days_imported = committed.hours // 24
            except NoRoomMeasureDevice:
                unmeasured.add(room_id)
                _LOGGER.debug("%s has no energy measuring device, skipped", room_name)
            except RateLimitError as err:
                manager.status = "rate_limited"
                manager.last_error = str(err)
                results["errors"].append(f"{room_name}: {err}")
                break
            except (
                APIError,
                CannotConnect,
                InvalidAuth,
                HistoryReplacementError,
                ValueError,
                TypeError,
                OSError,
            ) as err:
                manager.last_error = str(err)
                results["errors"].append(f"{room_name}: {err}")
                _LOGGER.warning("Hourly import failed for %s: %s", room_name, err)
            if prices is not None and room_id in confirmed:
                if manager._cancelled:
                    raise asyncio.CancelledError
                try:
                    costs = hourly_costs(confirmed[room_id], prices)
                    await async_write_costs(
                        hass,
                        cost_metadata(home_id, room_id, room_name, currency),
                        costs,
                    )
                    costed[room_id] = costs
                except (CostPriceError, HistoryReplacementError) as err:
                    cost_errors.append(f"{room_name} cost: {err}")
                    _LOGGER.warning("Hourly cost failed for %s: %s", room_name, err)
            manager.rooms_completed += 1
            if bulk is None and manager.rooms_completed < len(rooms):
                await asyncio.sleep(API_DELAY_SECONDS)
        if room_filter is None and rooms:
            missing = [
                name for rid, name in rooms
                if rid not in confirmed and rid not in unmeasured
            ]
            if missing:
                results["home_total"] = "incomplete"
                results["errors"].append(
                    "Home hourly total kept at its last complete value; missing: "
                    + ", ".join(missing)
                )
            elif not (total := sum_hourly(confirmed)):
                results["home_total"] = "incomplete"
            else:
                if manager._cancelled:
                    raise asyncio.CancelledError
                try:
                    await async_replace_external_history(
                        hass,
                        home_metadata(home_id, intuis_home.name),
                        hourly_windows(total),
                    )
                    results["home_total"] = home_total_status(
                        total, (end - start) // HOUR
                    )
                except HistoryReplacementError as err:
                    results["home_total"] = "incomplete"
                    results["errors"].append(f"Home hourly total: {err}")
        if prices is not None and room_filter is None and rooms:
            missing = [
                name for rid, name in rooms if rid not in costed and rid not in unmeasured
            ]
            if missing:
                cost_errors.append(
                    "Home hourly cost kept at its last complete value; missing: "
                    + ", ".join(missing)
                )
            elif total_cost := sum_hourly(costed):
                if manager._cancelled:
                    raise asyncio.CancelledError
                try:
                    await async_write_costs(
                        hass,
                        cost_metadata(home_id, None, intuis_home.name, currency),
                        total_cost,
                    )
                except HistoryReplacementError as err:
                    cost_errors.append(f"Home hourly cost: {err}")
        if cost_options:
            results["costs"] = (
                "complete" if not cost_errors else "partial" if costed else "failed"
            )
        manager.cost_status = results["costs"]
        manager.hourly_home_total = results["home_total"]
        if manager.status != "rate_limited":
            manager.status = (
                "partial"
                if results["errors"] and results["rooms_imported"]
                else "failed"
                if results["errors"]
                else "completed"
            )
    except asyncio.CancelledError:
        manager.status = "cancelled"
        raise
    except Exception as err:
        manager.status = "partial" if results["rooms_imported"] else "failed"
        manager.last_error = str(err)
        results["errors"].append(str(err))
        _LOGGER.exception("Hourly import failed")
    finally:
        if baselines is None and results["rooms_imported"]:
            # This import rebuilt absolute sums of its own; a level captured
            # before it no longer describes them, so the next cycle re-seeds.
            EnergyBase(manager._state).invalidate()
            await manager.async_save()
            _LOGGER.debug("Energy level invalidated after a manual hourly import")
        manager._running = False
        manager.current_room = None
        if manager._task is asyncio.current_task():
            manager._task = None
        if costed:
            # Display sensors only ever reflect acknowledged cost writes.
            async_publish_costs(hass, manager.entry_id)
    if results["errors"] or cost_errors:
        manager.last_error = "; ".join(results["errors"] + cost_errors)
    results["status"] = manager.status
    return results


class HourlyStatisticsUpdater:
    """Per-entry opt-in updater sharing the entry's import manager."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: IntuisAPI,
        intuis_home: IntuisHome,
        interval_minutes: int,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.api = api
        self.intuis_home = intuis_home
        self.interval = timedelta(minutes=interval_minutes)
        self._unsubscribers: list = []
        self._tick_task: asyncio.Task | None = None
        self._closed = False

    def async_start(self) -> None:
        self._closed = False
        self._unsubscribers = [
            async_call_later(self.hass, FIRST_UPDATE_DELAY, self._schedule),
            async_track_time_interval(self.hass, self._schedule, self.interval),
        ]

    @callback
    def _schedule(self, _now: datetime | None = None) -> None:
        """Start one update, in the event loop.

        Without @callback, Home Assistant runs a timer listener in an executor
        thread, where creating a task is refused.
        """
        if self._closed or (self._tick_task and not self._tick_task.done()):
            return
        self._tick_task = self.hass.async_create_task(self._async_tick())

    async def _async_tick(self) -> None:
        try:
            await self.async_update()
        except Exception:  # A failed cycle is retried at the next interval.
            _LOGGER.warning("Hourly statistics update failed", exc_info=True)

    async def async_update(self) -> bool:
        """Reserve the entry's manager; a running manual import defers this cycle.

        The daily rebase runs first, under the same reservation, so the hours
        written next are anchored on a level the cloud has settled instead of
        on whatever row happens to precede them.
        """
        from .history_import import async_get_import_manager

        if self._closed:
            return False
        manager = await async_get_import_manager(self.hass, self.entry.entry_id)
        now = datetime.now(timezone.utc)
        room_ids = [room_id for room_id, _ in energy_rooms(self.intuis_home)]
        zone = None
        try:
            zone = ZoneInfo(self.api.home_timezone)
            outcome = await manager.async_run_exclusive(
                async_rebase_levels(
                    self.hass, self.api, self.intuis_home, manager, zone, now
                )
            )
            if outcome is None:
                # async_run_exclusive closes the coroutine without running it,
                # so the rebase itself cannot report this.
                _LOGGER.debug(
                    "Energy rebase deferred: import running or entry unloading"
                )
        except Exception:  # noqa: BLE001 - the hourly pass must still run
            _LOGGER.warning("Energy rebase failed; hours stay relative", exc_info=True)
        if self._closed:
            return False
        start, end = await async_update_window(
            self.hass, self.intuis_home.id, room_ids, now
        )
        baselines = self._anchored_window(manager, zone, room_ids, end)
        if baselines is not None:
            start, baselines = baselines
        if self._closed:
            return False
        started = manager.start(
            self.api,
            self.intuis_home,
            granularity="hourly",
            start=start,
            end=end,
            home_id=self.intuis_home.id,
            cost_options=entry_cost_options(self.entry.options),
            baselines=baselines,
        )
        if not started:
            _LOGGER.debug("Hourly update deferred: import running or entry unloading")
        return started

    def _anchored_window(
        self,
        manager: HistoryImportManager,
        zone: ZoneInfo | None,
        room_ids: list[str],
        end: int,
    ) -> tuple[int, dict[str, float]] | None:
        """Window starting at the settled level, when every room has one.

        All or nothing: anchoring some rooms and not others would mix absolute
        and relative sums inside one home total.
        """
        if zone is None or not room_ids:
            return None
        base = EnergyBase(manager._state)
        start = base.hourly_start(zone)
        if start is None or start >= end:
            return None
        levels: dict[str, float] = {}
        for room_id in room_ids:
            level = base.level(room_id)
            if level is None:
                return None
            levels[room_id] = level
        return start, levels

    async def async_close(self) -> None:
        """Stop scheduling before the import manager drains its job."""
        self._closed = True
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers = []
        if self._tick_task is not None and not self._tick_task.done():
            self._tick_task.cancel()
            try:
                await self._tick_task
            except asyncio.CancelledError:
                pass
