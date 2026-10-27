"""Atomic, acknowledged energy-history replacement on HA's recorder thread.

A replacement covers one or more windows of confirmed data. Periods between
windows have no confirmed measurement: their rows are kept, never zeroed.

The adapter deliberately refuses an import without a live short-term anchor.
HA continues a total_increasing sensor from short-term statistics, not hourly
history; fabricating a reset at midnight would corrupt counters reset at 02:00.

External hourly series (TheFab21's #17/#22, adapted) own their statistic_id, so
they need no live anchor: sums continue from the row before the period.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import math
import threading
from typing import Any

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.db_schema import (
    Statistics,
    StatisticsMeta,
    StatisticsShortTerm,
)
from homeassistant.components.recorder.tasks import RecorderTask
from sqlalchemy import delete, select, update

from .utils.const import DOMAIN

HOUR = 3600


class HistoryReplacementError(Exception):
    """History cannot safely be replaced; the previous transaction is preserved."""


@dataclass(frozen=True)
class ReplacementResult:
    """Committed replacement, never merely a queued import."""

    days: int
    energy_kwh: float
    final_sum: float
    cleared: int
    adjusted: int


@dataclass(frozen=True)
class ExternalReplacementResult:
    """Committed external hourly replacement (kWh or currency)."""

    statistic_id: str
    hours: int
    total: float
    final_sum: float
    cleared: int
    adjusted: int
    created: bool


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


# A replacement period: [start, end) and its confirmed samples, all inside it.
Window = tuple[datetime, datetime, tuple[tuple[datetime, float], ...]]


def _replace_windows(
    session: Any,
    tables: tuple[type, ...],
    metadata_id: int,
    windows: tuple[Window, ...],
    cancelled: threading.Event,
) -> tuple[float, int, int]:
    """Replace each window in order; rows between windows keep their values.

    A gap is a period without confirmed data: its rows are neither deleted nor
    fabricated, they only follow the sum offset like every later row.
    Returns the final cumulative sum, cleared and adjusted row counts.
    """

    def sum_before(boundary: float) -> float:
        candidates = [
            session.scalar(
                select(table)
                .where(table.metadata_id == metadata_id, table.start_ts < boundary)
                .order_by(table.start_ts.desc())
                .limit(1)
            )
            for table in tables
        ]
        existing = [row for row in candidates if row is not None]
        return max(existing, key=lambda row: row.start_ts).sum if existing else 0.0

    cumulative = 0.0
    cleared = adjusted = 0
    for start, end, samples in windows:
        start_ts, end_ts = start.timestamp(), end.timestamp()
        baseline = sum_before(start_ts)
        old_final = sum_before(end_ts)
        if not _finite(baseline) or not _finite(old_final):
            raise HistoryReplacementError(
                "Existing cumulative sums are invalid; history was preserved"
            )
        if cancelled.is_set():
            raise asyncio.CancelledError
        cumulative = baseline
        rows = []
        for timestamp, value in samples:
            cumulative += value
            if not math.isfinite(cumulative):
                raise HistoryReplacementError("Cumulative value is not finite")
            rows.append(
                Statistics.from_stats(
                    metadata_id, {"start": timestamp, "state": value, "sum": cumulative}
                )
            )
        for table in tables:
            cleared += session.execute(
                delete(table).where(
                    table.metadata_id == metadata_id,
                    table.start_ts >= start_ts,
                    table.start_ts < end_ts,
                )
            ).rowcount
        session.add_all(rows)
        # Later rows keep their own increments; only their offset follows.
        delta = cumulative - old_final
        if delta:
            for table in tables:
                adjusted += session.execute(
                    update(table)
                    .where(table.metadata_id == metadata_id, table.start_ts >= end_ts)
                    .values(sum=table.sum + delta)
                ).rowcount
        # The next window's baseline must see this window's rows.
        session.flush()
    if cancelled.is_set():
        raise asyncio.CancelledError
    return cumulative, cleared, adjusted


def _all_samples(windows: tuple[Window, ...]) -> list[tuple[datetime, float]]:
    return [sample for _, _, samples in windows for sample in samples]


def _replace_in_transaction(
    instance: Any,
    entity_id: str,
    windows: tuple[Window, ...],
    cancelled: threading.Event,
) -> ReplacementResult:
    """Run only on the recorder worker; any exception rolls back all changes."""
    end_ts = windows[-1][1].timestamp()
    with instance.get_session() as session, session.begin():
        meta = session.scalar(
            select(StatisticsMeta).where(StatisticsMeta.statistic_id == entity_id)
        )
        if (
            meta is None
            or meta.source != "recorder"
            or meta.unit_of_measurement != "kWh"
            or not meta.has_sum
        ):
            raise HistoryReplacementError(
                "No compatible kWh recorder metadata; wait for live sensor statistics, then retry the import"
            )
        # The latest live anchor must survive deletion. Keeping its ID also keeps
        # HA's short-term run cache valid. Do not create synthetic reset states.
        anchor = session.scalar(
            select(StatisticsShortTerm)
            .where(
                StatisticsShortTerm.metadata_id == meta.id,
                StatisticsShortTerm.start_ts >= end_ts,
            )
            .order_by(StatisticsShortTerm.start_ts.desc())
            .limit(1)
        )
        if anchor is None or not _finite(anchor.sum) or not _finite(anchor.state):
            raise HistoryReplacementError(
                "No valid live short-term baseline after the import period; wait for live statistics, then retry the import"
            )
        # The first post-import state is a daily counter, not a consumption
        # delta, so already-recorded increments after a window are preserved.
        final_sum, cleared, adjusted = _replace_windows(
            session, (Statistics, StatisticsShortTerm), meta.id, windows, cancelled
        )
        samples = _all_samples(windows)
        result = ReplacementResult(
            len(samples),
            sum(value for _, value in samples),
            final_sum,
            cleared,
            adjusted,
        )
    return result


def _replace_external_in_transaction(
    instance: Any,
    meta_data: dict[str, Any],
    windows: tuple[Window, ...],
    cancelled: threading.Event,
) -> ExternalReplacementResult:
    """Replace one external series; metadata creation shares the rollback."""
    statistic_id = meta_data["statistic_id"]
    with instance.get_session() as session, session.begin():
        meta = session.scalar(
            select(StatisticsMeta).where(StatisticsMeta.statistic_id == statistic_id)
        )
        created = meta is None
        if created:
            # Not via the metadata manager: its cache must never learn an ID
            # that a rollback discards. HA reloads the row from the database.
            meta = StatisticsMeta.from_meta(meta_data)
            session.add(meta)
            session.flush()
        elif (
            meta.source != DOMAIN
            or meta.unit_of_measurement != meta_data["unit_of_measurement"]
            or not meta.has_sum
        ):
            raise HistoryReplacementError(
                "Existing external statistics metadata is incompatible; history was preserved"
            )
        final_sum, cleared, adjusted = _replace_windows(
            session, (Statistics,), meta.id, windows, cancelled
        )
        samples = _all_samples(windows)
        result = ExternalReplacementResult(
            statistic_id,
            len(samples),
            sum(value for _, value in samples),
            final_sum,
            cleared,
            adjusted,
            created,
        )
    return result


@dataclass
class _AcknowledgedTask(RecorderTask):
    transaction: Callable[[Any, threading.Event], Any]
    cancelled: threading.Event
    future: asyncio.Future
    loop: asyncio.AbstractEventLoop

    def run(self, instance: Any) -> None:
        """Acknowledge only after commit or rollback, without killing the worker."""
        try:
            result = self.transaction(instance, self.cancelled)
        except asyncio.CancelledError as err:
            self.loop.call_soon_threadsafe(self._finish, None, err)
        except Exception as err:
            # Transaction exit has rolled back before the acknowledgement.
            error = HistoryReplacementError(f"Recorder replacement failed: {err}")
            self.loop.call_soon_threadsafe(self._finish, None, error)
        else:
            self.loop.call_soon_threadsafe(self._finish, result, None)

    def _finish(self, result: Any, error: BaseException | None) -> None:
        if self.future.done():
            return
        if error is not None:
            self.future.set_exception(error)
        else:
            self.future.set_result(result)


def _running_instance(hass: Any) -> Any:
    instance = get_instance(hass)
    if not callable(getattr(instance, "queue_task", None)) or not callable(
        getattr(instance, "get_session", None)
    ):
        raise HistoryReplacementError(
            "Recorder does not support acknowledged transactional replacement"
        )
    if (
        not callable(getattr(instance, "is_alive", None))
        or not instance.is_alive()
        or not getattr(instance, "recording", False)
        or getattr(instance, "stop_requested", False)
    ):
        raise HistoryReplacementError(
            "Recorder worker is not running; history was preserved"
        )
    return instance


def _validate_samples(
    start: datetime,
    end: datetime,
    samples: tuple[tuple[datetime, float], ...],
    *,
    allow_negative: bool = False,
) -> None:
    if not samples or start.tzinfo is None or end.tzinfo is None or start >= end:
        raise HistoryReplacementError("Invalid or empty replacement period")
    previous_ts = None
    for timestamp, energy in samples:
        if not isinstance(timestamp, datetime) or timestamp.tzinfo is None:
            raise HistoryReplacementError("Sample timestamps must be timezone-aware")
        ts = timestamp.timestamp()
        if not math.isfinite(ts) or not start.timestamp() <= ts < end.timestamp():
            raise HistoryReplacementError(
                "Sample timestamp lies outside the replacement period"
            )
        if previous_ts is not None and ts <= previous_ts:
            raise HistoryReplacementError(
                "Sample timestamps must be unique and chronological"
            )
        if not _finite(energy) or (energy < 0 and not allow_negative):
            raise HistoryReplacementError(
                "Sample energy must be finite and nonnegative"
            )
        previous_ts = ts


def _validate_windows(
    windows: tuple[Window, ...], *, allow_negative: bool = False
) -> tuple[Window, ...]:
    """Chronological, disjoint, hour-aligned windows, each with valid samples.

    The recorder only stores rows that start on the hour, so every window
    boundary and sample must too; anything else is refused before queueing.
    """
    windows = tuple(windows)
    if not windows:
        raise HistoryReplacementError("Invalid or empty replacement period")
    previous_end = None
    for start, end, samples in windows:
        _validate_samples(start, end, samples, allow_negative=allow_negative)
        if previous_end is not None and start < previous_end:
            raise HistoryReplacementError(
                "Replacement windows must be chronological and disjoint"
            )
        if any(
            moment.timestamp() % HOUR
            for moment in (start, end, *(timestamp for timestamp, _ in samples))
        ):
            raise HistoryReplacementError(
                "Replacement boundaries and samples must start on the hour"
            )
        previous_end = end
    return windows


async def _async_acknowledged(
    instance: Any, transaction: Callable[[Any, threading.Event], Any]
) -> Any:
    """Queue a single transaction and wait for its actual completion.

    On cancellation, signal rollback and drain the worker acknowledgement. A
    commit already in progress may complete, but never after unload has returned.
    """
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    cancelled = threading.Event()
    instance.queue_task(_AcknowledgedTask(transaction, cancelled, future, loop))
    try:
        return await asyncio.shield(future)
    except asyncio.CancelledError:
        cancelled.set()
        # Shield prevents caller cancellation from discarding the acknowledgement.
        # Consume further cancellation requests while the recorder completes.
        while not future.done():
            try:
                await asyncio.shield(future)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if future.done() and not future.cancelled():
            future.exception()  # consume a rollback/write exception if cancelled
        raise


async def async_replace_energy_history(
    hass: Any,
    entity_id: str,
    windows: tuple[Window, ...],
) -> ReplacementResult:
    """Replace a daily sensor's measured windows in one acknowledged transaction.

    Days between windows had no measurement: their rows are preserved.
    """
    instance = _running_instance(hass)
    windows = _validate_windows(windows)
    return await _async_acknowledged(
        instance,
        lambda worker, cancelled: _replace_in_transaction(
            worker, entity_id, windows, cancelled
        ),
    )


async def async_replace_external_history(
    hass: Any,
    meta_data: dict[str, Any],
    windows: tuple[Window, ...],
) -> ExternalReplacementResult:
    """Replace the confirmed hours of an external series in one transaction.

    Each window must be complete: a hole inside it would silently delete
    confirmed hours. Hours between windows are unconfirmed and preserved.
    Replaying the same samples rewrites identical rows and adjusts nothing.
    Energy series are in kWh and nonnegative; cost series are in a currency
    and may be negative (negative tariffs).
    """
    instance = _running_instance(hass)
    sid = str(meta_data.get("statistic_id", ""))
    unit = meta_data.get("unit_of_measurement")
    is_cost = sid.startswith(f"{DOMAIN}:cost_")
    if (
        meta_data.get("source") != DOMAIN
        or not sid.startswith(f"{DOMAIN}:")
        or meta_data.get("has_sum") is not True
        or not (
            (is_cost and isinstance(unit, str) and unit and unit != "kWh")
            or (sid.startswith(f"{DOMAIN}:energy_") and unit == "kWh")
        )
    ):
        raise HistoryReplacementError("Invalid external statistics metadata")
    windows = _validate_windows(windows, allow_negative=is_cost)
    for start, end, samples in windows:
        if [timestamp.timestamp() for timestamp, _ in samples] != [
            float(ts)
            for ts in range(int(start.timestamp()), int(end.timestamp()), HOUR)
        ]:
            raise HistoryReplacementError("External hourly coverage must be complete")
    return await _async_acknowledged(
        instance,
        lambda worker, cancelled: _replace_external_in_transaction(
            worker, meta_data, windows, cancelled
        ),
    )
