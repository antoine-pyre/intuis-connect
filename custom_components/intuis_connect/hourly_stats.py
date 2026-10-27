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

from homeassistant.components.recorder import get_instance, statistics
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_call_later, async_track_time_interval

from .cost_stats import (
    CostPriceError,
    async_hour_prices,
    async_publish_costs,
    async_write_costs,
    cost_metadata,
    hourly_costs,
)
from .external_statistics import metadata, statistic_id
from .hourly_series import (
    HOUR,
    closed_hour_end,
    home_total_status,
    hourly_windows,
    stage_hourly,
    sum_hourly,
)
from .intuis_api.api import APIError, CannotConnect, InvalidAuth, RateLimitError
from .recorder_import import HistoryReplacementError, async_replace_external_history
from .utils.const import CONF_COST_STATISTICS

if TYPE_CHECKING:
    from .entity.intuis_home import IntuisHome
    from .history_import import HistoryImportManager
    from .intuis_api.api import IntuisAPI

_LOGGER = logging.getLogger(__name__)
UPDATE_WINDOW = 48 * HOUR
CATCH_UP_WINDOW = 7 * 24 * HOUR
FIRST_UPDATE_DELAY = 60  # seconds; lets the recorder and first refresh settle


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
        rooms = [
            (room_id, room.name)
            for room_id, room in intuis_home.rooms.items()
            if not room_filter or room.name.casefold() == room_filter.casefold()
        ]
        manager.total_rooms = len(rooms)
        manager.total_days = (end - start) // 86400
        if not rooms:
            results["errors"].append("No matching rooms")
        confirmed: dict[str, tuple[tuple[datetime, float], ...]] = {}
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
        for room_id, room_name in rooms:
            if manager._cancelled:
                raise asyncio.CancelledError
            manager.current_room = room_name
            try:
                values = await api.async_get_room_energy_hourly(room_id, start, end)
                samples = stage_hourly(values, start, end)
                if manager._cancelled:
                    raise asyncio.CancelledError
                committed = await async_replace_external_history(
                    hass,
                    room_metadata(home_id, room_id, room_name),
                    hourly_windows(samples),
                )
                confirmed[room_id] = samples
                results["rooms_imported"] += 1
                results["total_energy_kwh"] += committed.total
                manager.days_imported = committed.hours // 24
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
            if manager.rooms_completed < len(rooms):
                await asyncio.sleep(API_DELAY_SECONDS)
        if room_filter is None and rooms:
            missing = [name for rid, name in rooms if rid not in confirmed]
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
            missing = [name for rid, name in rooms if rid not in costed]
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

    def _schedule(self, _now: datetime | None = None) -> None:
        if self._closed or (self._tick_task and not self._tick_task.done()):
            return
        self._tick_task = self.hass.async_create_task(self._async_tick())

    async def _async_tick(self) -> None:
        try:
            await self.async_update()
        except Exception:  # A failed cycle is retried at the next interval.
            _LOGGER.warning("Hourly statistics update failed", exc_info=True)

    async def async_update(self) -> bool:
        """Reserve the entry's manager; a running manual import defers this cycle."""
        from .history_import import async_get_import_manager

        if self._closed:
            return False
        manager = await async_get_import_manager(self.hass, self.entry.entry_id)
        start, end = await async_update_window(
            self.hass,
            self.intuis_home.id,
            list(self.intuis_home.rooms),
            datetime.now(timezone.utc),
        )
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
        )
        if not started:
            _LOGGER.debug("Hourly update deferred: import running or entry unloading")
        return started

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
