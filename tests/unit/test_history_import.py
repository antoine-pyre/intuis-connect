"""History imports exercise the importer and HA's actual recorder worker."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from homeassistant.components.recorder.core import Recorder
from homeassistant.components.recorder.db_schema import (
    Statistics,
    StatisticsMeta,
    StatisticsShortTerm,
)
from homeassistant.components.recorder import statistics
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.recorder import async_initialize_recorder
from sqlalchemy import event, select

from custom_components.intuis_connect import async_unload_entry, update_listener
from custom_components.intuis_connect.history_import import (
    HistoryImportManager,
    _closed_day_range,
    _validate_daily_values,
    async_import_energy_history,
)
from custom_components.intuis_connect.intuis_api.api import (
    CannotConnect,
    RateLimitError,
)
from custom_components.intuis_connect.recorder_import import (
    HistoryReplacementError,
    async_replace_energy_history,
)
from custom_components.intuis_connect.utils.const import DOMAIN, CONF_IMPORT_HISTORY


@pytest.fixture
async def live_recorder(ha_hass, tmp_path):
    """Start HA's real recorder thread/queue and SQLite schema, without cloud setup."""
    async_initialize_recorder(ha_hass)
    instance = Recorder(
        hass=ha_hass,
        auto_purge=False,
        auto_repack=False,
        keep_days=730,
        commit_interval=1,
        uri=f"sqlite:///{tmp_path / 'history-recorder.db'}",
        db_max_retries=1,
        db_retry_wait=1,
        entity_filter=lambda _: True,
        exclude_event_types=set(),
    )
    ha_hass.data["recorder_instance"] = instance
    instance.async_initialize()
    instance.async_register()
    instance.start()
    assert await asyncio.wait_for(instance.async_db_ready, 15)
    instance._async_hass_started(ha_hass)
    await asyncio.wait_for(instance.async_recorder_ready.wait(), 15)
    yield instance
    if instance.is_alive():
        await instance.async_block_till_done()
    # HA fixture shutdown invokes recorder's registered FINAL_WRITE/CLOSE hooks.


def instant(day, hour=0):
    return datetime(2026, 10, day, hour, tzinfo=timezone.utc)


async def seed(instance, *, unit="kWh", anchor=True, anchor_state=1.0, anchor_sum=23.0):
    """Populate real rows outside, inside and after a two-day replacement."""

    def insert():
        with instance.get_session() as session, session.begin():
            meta = StatisticsMeta(
                statistic_id="sensor.room_energy",
                source="recorder",
                unit_of_measurement=unit,
                has_sum=True,
                has_mean=False,
            )
            session.add(meta)
            session.flush()
            for day, hour, state, total in [
                (22, 23, 7, 10),
                (23, 0, 4, 14),
                (24, 0, 8, 22),
                (25, 0, 1, 23),
                (25, 2, 2, 24),
            ]:
                session.add(
                    Statistics(
                        metadata_id=meta.id,
                        start_ts=instant(day, hour).timestamp(),
                        state=state,
                        sum=total,
                    )
                )
            session.add(
                StatisticsShortTerm(
                    metadata_id=meta.id,
                    start_ts=instant(24, 23).timestamp(),
                    state=8,
                    sum=22,
                )
            )
            if anchor:
                session.add(
                    StatisticsShortTerm(
                        metadata_id=meta.id,
                        start_ts=instant(25).timestamp(),
                        state=anchor_state,
                        sum=anchor_sum,
                    )
                )
            return meta.id

    return await instance.async_add_executor_job(insert)


async def rows(instance, table=Statistics):
    def read():
        with instance.get_session() as session:
            return [
                (r.start_ts, r.state, r.sum)
                for r in session.scalars(select(table).order_by(table.start_ts))
            ]

    return await instance.async_add_executor_job(read)


async def replace(ha_hass, values=(2.0, 0.0)):
    return await async_replace_energy_history(
        ha_hass,
        "sensor.room_energy",
        instant(23),
        instant(25),
        ((instant(23), values[0]), (instant(24), values[1])),
    )


async def test_real_worker_replaces_atomically_and_reimport_is_idempotent(
    ha_hass, live_recorder
):
    await seed(live_recorder)
    committed = await replace(ha_hass)
    assert (
        committed.days == 2 and committed.energy_kwh == 2 and committed.final_sum == 12
    )
    expected = [
        (instant(22, 23).timestamp(), 7, 10),
        (instant(23).timestamp(), 2, 12),
        (instant(24).timestamp(), 0, 12),
        (instant(25).timestamp(), 1, 13),
        (instant(25, 2).timestamp(), 2, 14),
    ]
    assert await rows(live_recorder) == expected
    assert await rows(live_recorder, StatisticsShortTerm) == [
        (instant(25).timestamp(), 1, 13)
    ]
    again = await replace(ha_hass)
    assert again.final_sum == 12 and again.adjusted == 0
    assert await rows(live_recorder) == expected


async def test_worker_rollback_preserves_long_and_short_statistics(
    ha_hass, live_recorder
):
    await seed(live_recorder)
    before, before_short = (
        await rows(live_recorder),
        await rows(live_recorder, StatisticsShortTerm),
    )

    def fail_insert(conn, cursor, statement, parameters, context, many):
        if statement.startswith("INSERT INTO statistics "):
            raise RuntimeError("injected insertion failure")

    event.listen(live_recorder.engine, "before_cursor_execute", fail_insert)
    try:
        with pytest.raises(HistoryReplacementError, match="injected insertion failure"):
            await replace(ha_hass)
    finally:
        event.remove(live_recorder.engine, "before_cursor_execute", fail_insert)
    assert await rows(live_recorder) == before
    assert await rows(live_recorder, StatisticsShortTerm) == before_short
    # The worker survived the failed custom task and can process the next job.
    assert (await replace(ha_hass)).final_sum == 12


@pytest.mark.parametrize(
    "kwargs",
    [
        {"anchor": False},
        {"unit": "Wh"},
        {"anchor_state": None},
        {"anchor_sum": float("inf")},
    ],
)
async def test_unsafe_live_baseline_refuses_without_mutation(
    ha_hass, live_recorder, kwargs
):
    await seed(live_recorder, **kwargs)
    before = await rows(live_recorder)
    with pytest.raises(HistoryReplacementError, match="baseline|metadata"):
        await replace(ha_hass)
    assert await rows(live_recorder) == before


async def test_latest_short_term_cache_and_live_increment_survive_import(
    ha_hass, live_recorder
):
    await seed(live_recorder)

    def latest():
        with live_recorder.get_session() as session:
            return statistics.get_latest_short_term_statistics_with_session(
                ha_hass,
                session,
                {"sensor.room_energy"},
                {"sum", "state"},
            )["sensor.room_energy"][0]

    before = await live_recorder.async_add_executor_job(latest)
    assert before["sum"] == 23
    await replace(ha_hass)
    after = await live_recorder.async_add_executor_job(latest)
    assert after["state"] == before["state"] == 1 and after["sum"] == 13
    # Exercise HA's actual sensor statistics compiler, not copied arithmetic.
    from homeassistant.components.sensor import recorder as sensor_recorder

    ha_hass.states.async_set(
        "sensor.room_energy",
        1.5,
        {
            "state_class": "total_increasing",
            "unit_of_measurement": "kWh",
            "device_class": "energy",
        },
    )
    await ha_hass.async_block_till_done()
    await live_recorder.async_block_till_done()
    now = datetime.now(timezone.utc)
    period_start = now.replace(minute=now.minute // 5 * 5, second=0, microsecond=0)

    def compile_live():
        import inspect

        kwargs = {}
        if (
            "custom_units_for_entities"
            in inspect.signature(sensor_recorder.compile_statistics).parameters
        ):
            kwargs["custom_units_for_entities"] = {}
        with live_recorder.get_session() as session:
            return sensor_recorder.compile_statistics(
                ha_hass,
                session,
                period_start,
                period_start + timedelta(minutes=5),
                **kwargs,
            )

    compiled = await live_recorder.async_add_executor_job(compile_live)
    assert compiled.platform_stats[0]["stat"]["sum"] == 13.5


def test_closed_days_follow_local_midnight_and_dst():
    zone = ZoneInfo("Europe/Paris")
    start, end = _closed_day_range(
        datetime(2026, 10, 26, 12, tzinfo=timezone.utc), 2, zone
    )
    values = [
        (int(datetime(2026, 10, 24, tzinfo=zone).timestamp()), 1000),
        (int(datetime(2026, 10, 25, tzinfo=zone).timestamp()), 0),
    ]
    samples = _validate_daily_values(values, start, end)
    assert samples[0][1] == 1 and samples[1][1] == 0
    assert int(end.timestamp()) - int(samples[-1][0].timestamp()) == 25 * 3600
    spring_start, spring_end = _closed_day_range(
        datetime(2026, 3, 30, 12, tzinfo=timezone.utc), 1, zone
    )
    assert spring_end.timestamp() - spring_start.timestamp() == 23 * 3600


@pytest.mark.parametrize(
    "values",
    [
        [],
        [(instant(23).timestamp(), 0)],
        [(instant(23).timestamp(), 0), (instant(23).timestamp(), 1)],
        [(instant(23).timestamp(), -1), (instant(24).timestamp(), 0)],
        [(instant(23).timestamp(), float("nan")), (instant(24).timestamp(), 0)],
        [(instant(23, 1).timestamp(), 0), (instant(24).timestamp(), 0)],
    ],
)
def test_invalid_or_incomplete_daily_coverage_is_rejected(values):
    with pytest.raises(HistoryReplacementError):
        _validate_daily_values(values, instant(23), instant(25))


async def importer_setup(ha_hass, monkeypatch, values, *, second=False):
    from homeassistant.helpers import device_registry as dr

    if hasattr(dr, "async_setup"):
        dr.async_setup(ha_hass)
    await dr.async_load(ha_hass)
    registry = er.async_get(ha_hass)
    await registry.async_load()
    registry.async_get_or_create(
        "sensor", DOMAIN, "intuis_home_room_energy", suggested_object_id="room_energy"
    )
    rooms = {"room": SimpleNamespace(name="Room")}
    if second:
        registry.async_get_or_create(
            "sensor",
            DOMAIN,
            "intuis_home_other_energy",
            suggested_object_id="other_energy",
        )
        rooms["other"] = SimpleNamespace(name="Other")
    api = SimpleNamespace(
        home_timezone="UTC", async_get_room_energy_daily=AsyncMock(side_effect=values)
    )
    home = SimpleNamespace(id="home", name="Test home", rooms=rooms)
    manager = HistoryImportManager(ha_hass, "entry")
    await manager.async_load()
    monkeypatch.setattr(
        "custom_components.intuis_connect.history_import.API_DELAY_SECONDS", 0
    )
    return api, home, manager


@pytest.mark.parametrize("error", [CannotConnect("offline"), RateLimitError("429"), []])
async def test_actual_importer_fetch_failures_preserve_existing_statistics(
    ha_hass, live_recorder, monkeypatch, frozen_clock, error
):
    frozen_clock.move_to("2026-10-25 12:00:00")
    await seed(live_recorder)
    before = await rows(live_recorder)
    api, home, manager = await importer_setup(ha_hass, monkeypatch, [error])
    result = await async_import_energy_history(ha_hass, api, home, manager, days=2)
    assert result["rooms_imported"] == 0 and result["errors"]
    assert result["status"] == (
        "rate_limited" if isinstance(error, RateLimitError) else "failed"
    )
    assert await rows(live_recorder) == before


async def test_importer_confirms_commit_and_reports_partial_failure(
    ha_hass, live_recorder, monkeypatch, frozen_clock
):
    frozen_clock.move_to("2026-10-25 12:00:00")
    await seed(live_recorder)
    api, home, manager = await importer_setup(
        ha_hass,
        monkeypatch,
        [
            [(instant(23).timestamp(), 2000), (instant(24).timestamp(), 0)],
            CannotConnect("offline"),
        ],
        second=True,
    )
    result = await async_import_energy_history(ha_hass, api, home, manager, days=2)
    assert result["status"] == "partial" and result["rooms_imported"] == 1
    assert manager.get_room_progress("room")["cumulative_sum"] == 12
    assert (await rows(live_recorder))[1][2] == 12


async def test_unload_cancels_fetch_and_disallows_restart(
    ha_hass, ha_entry_factory, live_recorder, monkeypatch
):
    await seed(live_recorder)
    entered = asyncio.Event()

    async def blocked(*args):
        entered.set()
        await asyncio.Event().wait()

    api, home, manager = await importer_setup(ha_hass, monkeypatch, [])
    api.async_get_room_energy_daily = blocked
    entry = ha_entry_factory()
    ha_hass.data[DOMAIN] = {
        entry.entry_id: {},
        "import_managers": {entry.entry_id: manager},
    }
    monkeypatch.setattr(
        ha_hass.config_entries, "async_unload_platforms", AsyncMock(return_value=True)
    )
    assert manager.start(api, home, days=2)
    assert not manager.start(api, home, days=2)
    await entered.wait()
    before = await rows(live_recorder)
    assert await async_unload_entry(ha_hass, entry)
    assert manager.status == "cancelled" and not manager.is_running
    assert not manager.start(api, home, days=2)
    assert await rows(live_recorder) == before


async def test_consuming_import_flag_does_not_reload_its_own_task(
    ha_hass, ha_entry_factory, monkeypatch
):
    entry = ha_entry_factory(options={CONF_IMPORT_HISTORY: False, "manual_duration": 5})
    ha_hass.data[DOMAIN] = {
        entry.entry_id: {"options": {CONF_IMPORT_HISTORY: True, "manual_duration": 5}}
    }
    reload = AsyncMock()
    monkeypatch.setattr(ha_hass.config_entries, "async_reload", reload)
    await update_listener(ha_hass, entry)
    reload.assert_not_awaited()
    ha_hass.data[DOMAIN][entry.entry_id]["options"] = {
        CONF_IMPORT_HISTORY: False,
        "manual_duration": 10,
    }
    await update_listener(ha_hass, entry)
    reload.assert_awaited_once_with(entry.entry_id)


async def test_direct_imports_release_manager_task_ownership(
    ha_hass, live_recorder, monkeypatch, frozen_clock
):
    frozen_clock.move_to("2026-10-25 12:00:00")
    await seed(live_recorder)
    values = [(instant(23).timestamp(), 2000), (instant(24).timestamp(), 0)]
    api, home, manager = await importer_setup(ha_hass, monkeypatch, [values, values])
    for _ in range(2):
        result = await async_import_energy_history(ha_hass, api, home, manager, days=2)
        assert result["status"] == "completed" and not manager.is_running
    assert manager._task is None
    await manager.async_close()  # Must never cancel the awaiting test/caller.


async def test_cancel_before_scheduled_import_starts_has_terminal_status(
    ha_hass, monkeypatch
):
    # Cover the non-eager scheduler case; current HA may start tasks eagerly.
    monkeypatch.setattr(
        ha_hass, "async_create_task", lambda coroutine: asyncio.create_task(coroutine)
    )
    api, home, manager = await importer_setup(ha_hass, monkeypatch, [])
    assert manager.start(api, home, days=2)
    await manager.async_close()
    assert not manager.is_running and manager.status == "cancelled"
    api.async_get_room_energy_daily.assert_not_awaited()


@pytest.mark.parametrize(
    "samples",
    [
        ((instant(22), 1),),
        ((instant(25), 1),),
        ((instant(23).replace(tzinfo=None), 1),),
        ((instant(24), 1), (instant(23), 1)),
        ((instant(23), 1), (instant(23), 1)),
        ((instant(23), -1),),
        ((instant(23), float("inf")),),
    ],
)
async def test_adapter_rejects_bad_staging_before_queue(
    ha_hass, live_recorder, monkeypatch, samples
):
    queued = AsyncMock()
    monkeypatch.setattr(live_recorder, "queue_task", queued)
    with pytest.raises(HistoryReplacementError):
        await async_replace_energy_history(
            ha_hass, "sensor.room_energy", instant(23), instant(25), samples
        )
    queued.assert_not_called()


async def test_unload_drains_inflight_transaction_and_rolls_back(
    ha_hass, ha_entry_factory, live_recorder, monkeypatch, frozen_clock
):
    import threading

    frozen_clock.move_to("2026-10-25 12:00:00")
    await seed(live_recorder)
    before = await rows(live_recorder)
    before_short = await rows(live_recorder, StatisticsShortTerm)
    values = [(instant(23).timestamp(), 2000), (instant(24).timestamp(), 0)]
    api, home, manager = await importer_setup(ha_hass, monkeypatch, [values])
    entry = ha_entry_factory()
    ha_hass.data[DOMAIN] = {
        entry.entry_id: {},
        "import_managers": {entry.entry_id: manager},
    }
    monkeypatch.setattr(
        ha_hass.config_entries, "async_unload_platforms", AsyncMock(return_value=True)
    )
    entered, release = threading.Event(), threading.Event()

    def pause_insert(conn, cursor, statement, parameters, context, many):
        if statement.startswith("INSERT INTO statistics "):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("test did not release recorder")

    event.listen(live_recorder.engine, "before_cursor_execute", pause_insert)
    try:
        assert manager.start(api, home, days=2)
        assert await asyncio.to_thread(entered.wait, 5)
        unload = asyncio.create_task(async_unload_entry(ha_hass, entry))
        await asyncio.sleep(0.01)
        assert not unload.done()  # Transaction has not acknowledged rollback yet.
        release.set()
        assert await asyncio.wait_for(unload, 5)
    finally:
        release.set()
        event.remove(live_recorder.engine, "before_cursor_execute", pause_insert)
    assert manager.status == "cancelled" and not manager.is_running
    assert await rows(live_recorder) == before
    assert await rows(live_recorder, StatisticsShortTerm) == before_short
    await live_recorder.async_block_till_done()
    assert await rows(live_recorder) == before


async def test_stopped_worker_refuses_without_queuing(
    ha_hass, live_recorder, monkeypatch
):
    await seed(live_recorder)
    await live_recorder._async_shutdown(None)
    assert not live_recorder.is_alive()
    queued = AsyncMock()
    with monkeypatch.context() as patch:
        patch.setattr(live_recorder, "queue_task", queued)
        with pytest.raises(HistoryReplacementError, match="not running"):
            await replace(ha_hass)
        queued.assert_not_called()


async def test_concurrent_import_services_share_one_manager_and_task(
    ha_hass, ha_entry_factory, monkeypatch
):
    from custom_components.intuis_connect.services import async_register_services

    api, home, _ = await importer_setup(ha_hass, monkeypatch, [])
    entered = asyncio.Event()

    async def blocked(*args):
        entered.set()
        await asyncio.Event().wait()

    api.async_get_room_energy_daily = AsyncMock(side_effect=blocked)
    entry = ha_entry_factory()
    home.schedules = []
    ha_hass.data[DOMAIN] = {entry.entry_id: {"api": api, "intuis_home": home}}
    await async_register_services(ha_hass, entry)
    await asyncio.gather(
        *(
            ha_hass.services.async_call(
                DOMAIN, "import_energy_history", {"days": 2}, blocking=True
            )
            for _ in range(2)
        )
    )
    await entered.wait()
    assert api.async_get_room_energy_daily.await_count == 1
    manager = ha_hass.data[DOMAIN]["import_managers"][entry.entry_id]
    await manager.async_close()
    assert manager.status == "cancelled" and not manager.is_running


async def test_failed_unload_leaves_manager_reusable(
    ha_hass, ha_entry_factory, monkeypatch
):
    api, home, manager = await importer_setup(ha_hass, monkeypatch, [])
    entry = ha_entry_factory()
    ha_hass.data[DOMAIN] = {
        entry.entry_id: {},
        "import_managers": {entry.entry_id: manager},
    }
    monkeypatch.setattr(
        ha_hass.config_entries, "async_unload_platforms", AsyncMock(return_value=False)
    )
    assert not await async_unload_entry(ha_hass, entry)
    assert ha_hass.data[DOMAIN]["import_managers"][entry.entry_id] is manager
    assert not manager._closing

    # A refused unload must not permanently disable future service imports.
    async def blocked(*args):
        await asyncio.Event().wait()

    api.async_get_room_energy_daily = blocked
    assert manager.start(api, home, days=2)
    await manager.async_close()


async def test_close_drains_progress_store_write(
    ha_hass, live_recorder, monkeypatch, frozen_clock
):
    frozen_clock.move_to("2026-10-25 12:00:00")
    await seed(live_recorder)
    values = [(instant(23).timestamp(), 2000), (instant(24).timestamp(), 0)]
    api, home, manager = await importer_setup(ha_hass, monkeypatch, [values])
    entered, release = asyncio.Event(), asyncio.Event()
    writes = []
    original_save = manager.store.async_save

    async def paused_save(payload):
        entered.set()
        await release.wait()
        await original_save(payload)
        writes.append("persisted")

    monkeypatch.setattr(manager.store, "async_save", paused_save)
    assert manager.start(api, home, days=2)
    await entered.wait()
    close = asyncio.create_task(manager.async_close())
    await asyncio.sleep(0)
    assert not close.done()
    release.set()
    await asyncio.wait_for(close, 5)
    assert writes == ["persisted"] and not manager.is_running
    assert manager.status == "cancelled"
    assert await manager.store.async_load() == {
        "rooms": {
            "room": {
                "last_imported_day": int(instant(25).timestamp()),
                "cumulative_sum": 12,
            }
        }
    }
