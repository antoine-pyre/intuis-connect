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

from .external_statistics import metadata, statistic_id
from .hourly_series import HOUR, closed_hour_end, stage_hourly
from .intuis_api.api import APIError, CannotConnect, InvalidAuth, RateLimitError
from .recorder_import import HistoryReplacementError, async_replace_external_history

if TYPE_CHECKING:
    from .entity.intuis_home import IntuisHome
    from .history_import import HistoryImportManager
    from .intuis_api.api import IntuisAPI

_LOGGER = logging.getLogger(__name__)
UPDATE_WINDOW = 48 * HOUR
CATCH_UP_WINDOW = 7 * 24 * HOUR
FIRST_UPDATE_DELAY = 60  # seconds; lets the recorder and first refresh settle


def _utc(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, timezone.utc)


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


def _home_total(
    confirmed: dict[str, tuple[tuple[datetime, float], ...]],
) -> tuple[tuple[datetime, float], ...]:
    """Sum rooms hour by hour; callers guarantee identical complete coverage."""
    series = list(confirmed.values())
    return tuple(
        (series[0][index][0], sum(room[index][1] for room in series))
        for index in range(len(series[0]))
    )


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
) -> dict:
    """Fetch, stage, then replace one external series transaction per room.

    The home total is written only when every room of the home was confirmed
    for the same hours; otherwise the last complete total is left untouched.
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
    }
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
                    _utc(start),
                    _utc(end),
                    samples,
                )
                confirmed[room_id] = samples
                results["rooms_imported"] += 1
                results["total_energy_kwh"] += committed.energy_kwh
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
            else:
                if manager._cancelled:
                    raise asyncio.CancelledError
                try:
                    await async_replace_external_history(
                        hass,
                        home_metadata(home_id, intuis_home.name),
                        _utc(start),
                        _utc(end),
                        _home_total(confirmed),
                    )
                    results["home_total"] = "complete"
                except HistoryReplacementError as err:
                    results["home_total"] = "incomplete"
                    results["errors"].append(f"Home hourly total: {err}")
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
    if results["errors"]:
        manager.last_error = "; ".join(results["errors"])
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
