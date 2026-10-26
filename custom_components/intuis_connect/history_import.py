"""Validate closed-day energy data before an atomic recorder replacement."""

from __future__ import annotations

import asyncio
from datetime import datetime, time, timedelta, timezone
import logging
import math
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store

from .intuis_api.api import APIError, CannotConnect, InvalidAuth, RateLimitError
from .recorder_import import HistoryReplacementError, async_replace_energy_history
from .utils.const import DOMAIN

if TYPE_CHECKING:
    from .entity.intuis_home import IntuisHome
    from .intuis_api.api import IntuisAPI

_LOGGER = logging.getLogger(__name__)
STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.history_import"
DEFAULT_HISTORY_DAYS = 365
MAX_HISTORY_DAYS = 730
API_DELAY_SECONDS = 2.0


def _closed_day_range(
    now: datetime, days: int, zone: ZoneInfo
) -> tuple[datetime, datetime]:
    """Use complete local days, excluding the live day and its partial total."""
    today = now.astimezone(zone).date()
    return (
        datetime.combine(today - timedelta(days=days), time.min, zone),
        datetime.combine(today, time.min, zone),
    )


def _validate_daily_values(
    daily_values: list[tuple[int, float]],
    start: datetime,
    end: datetime,
) -> tuple[tuple[datetime, float], ...]:
    """Require exactly one finite measurement for every closed local day.

    The API must return local-midnight timestamps. Gaps, duplicate days, shifted
    UTC day boundaries and partial days are refused without touching statistics.
    """
    expected = []
    day = start.date()
    while day < end.date():
        timestamp = datetime.combine(day, time.min, start.tzinfo)
        if timestamp.timestamp() % 3600:
            raise HistoryReplacementError(
                "Local day boundaries must align with recorder hourly statistics"
            )
        expected.append(int(timestamp.timestamp()))
        day += timedelta(days=1)
    if len(daily_values) != len(expected):
        raise HistoryReplacementError(
            "Incomplete daily coverage; previous history was preserved"
        )
    actual: dict[int, float] = {}
    for timestamp, wh in daily_values:
        if (
            isinstance(timestamp, bool)
            or not isinstance(timestamp, (int, float))
            or not math.isfinite(timestamp)
            or timestamp != int(timestamp)
            or isinstance(wh, bool)
            or not isinstance(wh, (int, float))
            or not math.isfinite(wh)
            or wh < 0
        ):
            raise HistoryReplacementError("Invalid daily timestamp or energy value")
        if timestamp in actual:
            raise HistoryReplacementError("Duplicate daily measurement")
        actual[int(timestamp)] = wh / 1000.0
    if set(actual) != set(expected):
        raise HistoryReplacementError(
            "Daily measurements do not match the complete local-day boundaries"
        )
    return tuple(
        (datetime.fromtimestamp(ts, timezone.utc), actual[ts]) for ts in expected
    )


async def _await_store_task(task: asyncio.Task):
    """Do not detach an executor-backed Store operation during cancellation."""
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if task.done() and not task.cancelled():
            task.exception()
        raise


class HistoryImportManager:
    """Own one entry's import task, cancellation and persisted progress."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}_{entry_id}")
        self._state: dict = {}
        self._running = False
        self._cancelled = False
        self._closing = False
        self._task: asyncio.Task | None = None
        self._load_task: asyncio.Task | None = None
        self._loaded = False
        self.status = "idle"
        self.current_room: str | None = None
        self.rooms_completed = 0
        self.total_rooms = 0
        self.days_imported = 0
        self.total_days = 0
        self.last_error: str | None = None

    async def async_load(self) -> None:
        if self._loaded:
            return
        if self._load_task is None:
            self._load_task = self.hass.async_create_task(self.store.async_load())
        data = await _await_store_task(self._load_task)
        if not self._loaded:
            self._state = data or {"rooms": {}}
            self._loaded = True

    async def async_save(self) -> None:
        await _await_store_task(
            self.hass.async_create_task(self.store.async_save(self._state))
        )

    def get_room_progress(self, room_id: str) -> dict:
        return self._state.get("rooms", {}).get(
            room_id, {"last_imported_day": 0, "cumulative_sum": 0.0}
        )

    def update_room_progress(
        self, room_id: str, last_day: int, cumulative_sum: float
    ) -> None:
        self._state.setdefault("rooms", {})[room_id] = {
            "last_imported_day": last_day,
            "cumulative_sum": cumulative_sum,
        }

    def clear_room_progress(self, room_id: str) -> None:
        self._state.get("rooms", {}).pop(room_id, None)

    @property
    def is_running(self) -> bool:
        return self._running or (self._task is not None and not self._task.done())

    def start(self, api: IntuisAPI, intuis_home: IntuisHome, **kwargs) -> bool:
        """Reserve the entry synchronously so concurrent service calls cannot race."""
        if self.is_running or self._closing:
            return False
        self._task = self.hass.async_create_task(
            async_import_energy_history(self.hass, api, intuis_home, self, **kwargs)
        )
        return True

    def cancel(self) -> None:
        self._cancelled = True
        if self._task is not None and not self._task.done():
            self.status = "cancelled"
            self._task.cancel()

    async def async_close(self) -> None:
        """Prevent new imports and drain even an in-flight recorder transaction."""
        self._closing = True
        self.cancel()
        if self._task is not None and self._task is not asyncio.current_task():
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._load_task is not None:
            try:
                await _await_store_task(self._load_task)
            except Exception:
                _LOGGER.warning(
                    "Unable to finish loading import progress during unload",
                    exc_info=True,
                )


async def async_get_import_manager(
    hass: HomeAssistant, entry_id: str
) -> HistoryImportManager:
    """Publish before awaiting storage so concurrent callers share ownership."""
    managers = hass.data.setdefault(DOMAIN, {}).setdefault("import_managers", {})
    manager = managers.get(entry_id)
    if manager is None:
        manager = managers[entry_id] = HistoryImportManager(hass, entry_id)
    await manager.async_load()
    return manager


async def async_import_energy_history(
    hass: HomeAssistant,
    api: IntuisAPI,
    intuis_home: IntuisHome,
    manager: HistoryImportManager,
    days: int = DEFAULT_HISTORY_DAYS,
    room_filter: str | None = None,
    home_id: str | None = None,
) -> dict:
    """Fetch, validate, then replace one closed-day history transaction per room."""
    if manager._running or manager._closing:
        return {"error": "Import already running or entry unloading"}
    manager._running = True
    manager._task = asyncio.current_task()
    manager._cancelled = False
    manager.status = "importing"
    manager.last_error = None
    manager.rooms_completed = manager.days_imported = manager.total_rooms = (
        manager.total_days
    ) = 0
    results = {"rooms_imported": 0, "total_energy_kwh": 0.0, "errors": []}
    try:
        days = int(max(1, min(days, MAX_HISTORY_DAYS)))
        zone = ZoneInfo(api.home_timezone)
        start, end = _closed_day_range(datetime.now(timezone.utc), days, zone)
        home_id = home_id or intuis_home.id
        registry = er.async_get(hass)
        rooms = []
        for room_id, room in intuis_home.rooms.items():
            if room_filter and room.name.casefold() != room_filter.casefold():
                continue
            entity_id = registry.async_get_entity_id(
                "sensor", DOMAIN, f"intuis_{home_id}_{room_id}_energy"
            )
            if entity_id:
                rooms.append((room_id, room.name, entity_id))
            else:
                results["errors"].append(
                    f"Energy sensor for {room.name} is not registered"
                )
        manager.total_rooms = len(rooms)
        manager.total_days = days
        if not rooms:
            results["errors"].append("No matching registered energy sensors")
        for room_id, room_name, entity_id in rooms:
            if manager._cancelled:
                raise asyncio.CancelledError
            manager.current_room = room_name
            try:
                daily_values = await api.async_get_room_energy_daily(
                    room_id, int(start.timestamp()), int(end.timestamp()) - 1
                )
                samples = _validate_daily_values(daily_values, start, end)
                if manager._cancelled:
                    raise asyncio.CancelledError
                committed = await async_replace_energy_history(
                    hass, entity_id, start, end, samples
                )
                results["rooms_imported"] += 1
                results["total_energy_kwh"] += committed.energy_kwh
                results["statistics_cleared"] = (
                    results.get("statistics_cleared", 0) + committed.cleared
                )
                results["statistics_adjusted"] = (
                    results.get("statistics_adjusted", 0) + committed.adjusted
                )
                manager.days_imported = committed.days
                manager.update_room_progress(
                    room_id, int(end.timestamp()), committed.final_sum
                )
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
                _LOGGER.warning("History import failed for %s: %s", room_name, err)
            manager.rooms_completed += 1
            await manager.async_save()
            if manager.rooms_completed < len(rooms):
                await asyncio.sleep(API_DELAY_SECONDS)
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
        _LOGGER.exception("History import failed")
    finally:
        manager._running = False
        manager.current_room = None
        if manager._task is asyncio.current_task():
            manager._task = None
    if results["errors"]:
        manager.last_error = "; ".join(results["errors"])
    results["status"] = manager.status
    return results
