"""Hourly import, opt-in updater, service granularity and home total contracts."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import voluptuous as vol

from custom_components.intuis_connect import async_unload_entry
from custom_components.intuis_connect.config_flow import IntuisOptionsFlow
from custom_components.intuis_connect.external_statistics import statistic_id
from custom_components.intuis_connect.history_import import HistoryImportManager
from custom_components.intuis_connect.hourly_series import closed_hour_end
from custom_components.intuis_connect.hourly_stats import (
    HourlyStatisticsUpdater,
    async_import_hourly_history,
    async_update_window,
)
from custom_components.intuis_connect.intuis_api.api import CannotConnect
from custom_components.intuis_connect.utils.const import (
    CONF_HOURLY_STATISTICS,
    CONF_HOURLY_STATISTICS_INTERVAL,
    DOMAIN,
)

from .test_history_import import live_recorder as _live_recorder
from .test_hourly_statistics import hour, series
from .test_multi_home_services import call, homes as _homes, setup_real_entry

H = 3600


@pytest.fixture
async def live_recorder(ha_hass, tmp_path):
    async for instance in _live_recorder.__wrapped__(ha_hass, tmp_path):
        yield instance


@pytest.fixture
async def homes(ha_hass, ha_entry_factory):
    return await _homes.__wrapped__(ha_hass, ha_entry_factory)


def ts(n):
    return int(hour(n).timestamp())


def wh(first, values):
    return [(ts(first + i), value) for i, value in enumerate(values)]


async def importer(ha_hass, monkeypatch, responses):
    monkeypatch.setattr(
        "custom_components.intuis_connect.history_import.API_DELAY_SECONDS", 0
    )
    api = SimpleNamespace(async_get_room_energy_hourly=AsyncMock(side_effect=responses))
    home = SimpleNamespace(
        id="home",
        name="House",
        rooms={"a": SimpleNamespace(name="Living"), "b": SimpleNamespace(name="Bed")},
    )
    manager = HistoryImportManager(ha_hass, "entry")
    await manager.async_load()
    return api, home, manager


async def run(ha_hass, api, home, manager, first, hours, **kwargs):
    return await async_import_hourly_history(
        ha_hass, api, home, manager, start=ts(first), end=ts(first + hours), **kwargs
    )


async def test_rooms_and_home_total_are_distinct_complete_series(
    ha_hass, live_recorder, monkeypatch
):
    api, home, manager = await importer(
        ha_hass, monkeypatch, [wh(0, (500, 0)), wh(0, (250, 1000))]
    )
    result = await run(ha_hass, api, home, manager, 0, 2)
    assert result["status"] == "completed" and result["home_total"] == "complete"
    assert [r[1:] for r in await series(live_recorder, statistic_id("home", "a"))] == [
        (0.5, 0.5),
        (0, 0.5),
    ]
    assert [r[1:] for r in await series(live_recorder, statistic_id("home", None))] == [
        (0.75, 0.75),
        (1.0, 1.75),
    ]
    # Daily sensors are not involved: only the three external series exist.
    api.async_get_room_energy_hourly.assert_any_await("a", ts(0), ts(2))


async def test_incomplete_room_keeps_last_complete_home_total(
    ha_hass, live_recorder, monkeypatch
):
    api, home, manager = await importer(
        ha_hass,
        monkeypatch,
        [wh(0, (500, 0)), wh(0, (250, 1000)), wh(0, (900, 900)), CannotConnect("x")],
    )
    await run(ha_hass, api, home, manager, 0, 2)
    total = await series(live_recorder, statistic_id("home", None))
    result = await run(ha_hass, api, home, manager, 0, 2)
    assert result["status"] == "partial" and result["home_total"] == "incomplete"
    assert manager.hourly_home_total == "incomplete"
    assert "Bed" in manager.last_error
    # The confirmed room is replaced; the home total is not replaced by a partial sum.
    assert [r[1] for r in await series(live_recorder, statistic_id("home", "a"))] == [
        0.9,
        0.9,
    ]
    assert await series(live_recorder, statistic_id("home", None)) == total


async def test_room_filter_never_writes_the_home_total(
    ha_hass, live_recorder, monkeypatch
):
    api, home, manager = await importer(ha_hass, monkeypatch, [wh(0, (500,))])
    result = await run(ha_hass, api, home, manager, 0, 1, room_filter="living")
    assert result["home_total"] == "skipped" and result["rooms_imported"] == 1
    assert await series(live_recorder, statistic_id("home", None)) is None
    api.async_get_room_energy_hourly.assert_awaited_once()


async def test_unmeasured_hour_keeps_its_statistics_until_a_later_run(
    ha_hass, live_recorder, monkeypatch
):
    # The cloud has not published hour 1 of room b yet: its confirmed hours are
    # written, and the home total only covers hours both rooms confirmed.
    api, home, manager = await importer(
        ha_hass, monkeypatch, [wh(0, (1000, 2000)), wh(0, (500,))]
    )
    result = await run(ha_hass, api, home, manager, 0, 2)
    assert result["status"] == "completed" and result["home_total"] == "partial"
    assert manager.hourly_home_total == "partial"
    assert await series(live_recorder, statistic_id("home", "b")) == [(ts(0), 0.5, 0.5)]
    assert await series(live_recorder, statistic_id("home", None)) == [
        (ts(0), 1.5, 1.5)
    ]
    # The next run sees hour 1 for both rooms and completes the same series.
    api.async_get_room_energy_hourly.side_effect = [
        wh(0, (1000, 2000)),
        wh(0, (500, 250)),
    ]
    result = await run(ha_hass, api, home, manager, 0, 2)
    assert result["home_total"] == "complete"
    assert await series(live_recorder, statistic_id("home", None)) == [
        (ts(0), 1.5, 1.5),
        (ts(1), 2.25, 3.75),
    ]


async def test_room_without_any_measurement_keeps_home_total(
    ha_hass, live_recorder, monkeypatch
):
    api, home, manager = await importer(ha_hass, monkeypatch, [wh(0, (1, 1)), []])
    result = await run(ha_hass, api, home, manager, 0, 2)
    assert result["home_total"] == "incomplete" and result["status"] == "partial"
    assert await series(live_recorder, statistic_id("home", "b")) is None
    assert await series(live_recorder, statistic_id("home", None)) is None


@pytest.mark.parametrize(
    "last,expected_start",
    [
        (None, -48),  # first enablement: 48 hours, older periods via the service
        (-100, -99),  # interruption: resume after the last confirmed hour
        (-500, -168),  # longer interruption: bounded to 7 days
        (-3, -48),  # recent data: re-read 48 hours for late cloud corrections
    ],
)
async def test_update_window_comes_from_recorder_and_is_bounded(
    ha_hass, live_recorder, monkeypatch, last, expected_start
):
    now = hour(200) + timedelta(minutes=20)
    end = closed_hour_end(now)
    if last is not None:
        api, home, manager = await importer(
            ha_hass, monkeypatch, [[(end + last * H, 1)], [(end + last * H, 1)]]
        )
        await async_import_hourly_history(
            ha_hass, api, home, manager, start=end + last * H, end=end + (last + 1) * H
        )
    start, stop = await async_update_window(ha_hass, "home", ["a", "b"], now)
    assert stop == end and start == end + expected_start * H


async def test_updater_defers_to_running_import_and_stops_on_close(
    ha_hass, ha_entry_factory, monkeypatch
):
    entry = ha_entry_factory(home_id="home")
    home = SimpleNamespace(
        id="home", name="House", rooms={"a": SimpleNamespace(name="A")}
    )
    manager = SimpleNamespace(start=Mock(side_effect=[False, True]))
    monkeypatch.setattr(
        "custom_components.intuis_connect.history_import.async_get_import_manager",
        AsyncMock(return_value=manager),
    )
    monkeypatch.setattr(
        "custom_components.intuis_connect.hourly_stats.async_update_window",
        AsyncMock(return_value=(0, 7200)),
    )
    updater = HourlyStatisticsUpdater(ha_hass, entry, "api", home, 120)
    assert not await updater.async_update()  # manual import running
    assert await updater.async_update()
    manager.start.assert_called_with(
        "api",
        home,
        granularity="hourly",
        start=0,
        end=7200,
        home_id="home",
        cost_options=None,
    )
    updater.async_start()
    await updater.async_close()
    assert not await updater.async_update() and manager.start.call_count == 2


async def test_two_entries_update_independently(ha_hass, ha_entry_factory, monkeypatch):
    managers = {}

    async def get_manager(hass, entry_id):
        return managers.setdefault(
            entry_id, SimpleNamespace(start=Mock(return_value=True))
        )

    monkeypatch.setattr(
        "custom_components.intuis_connect.history_import.async_get_import_manager",
        get_manager,
    )
    monkeypatch.setattr(
        "custom_components.intuis_connect.hourly_stats.async_update_window",
        AsyncMock(return_value=(0, 7200)),
    )
    updaters = [
        HourlyStatisticsUpdater(
            ha_hass,
            ha_entry_factory(home_id=home_id),
            api,
            SimpleNamespace(id=home_id, name=home_id, rooms={}),
            60,
        )
        for home_id, api in (("one", "api1"), ("two", "api2"))
    ]
    await updaters[0].async_close()
    assert not await updaters[0].async_update()
    assert await updaters[1].async_update()
    (only,) = managers.values()
    only.start.assert_called_once()
    assert only.start.call_args.args[0] == "api2"


async def test_setup_creates_updater_only_when_enabled(
    homes, ha_entry_factory, monkeypatch
):
    entry = await setup_real_entry(homes, monkeypatch)
    assert "hourly_updater" not in homes.hass.data[DOMAIN][entry.entry_id]
    await homes.hass.data[DOMAIN][entry.entry_id]["coordinator"].async_shutdown()

    enabled = ha_entry_factory(
        home_id="first",
        options={CONF_HOURLY_STATISTICS: True, CONF_HOURLY_STATISTICS_INTERVAL: 60},
    )
    await setup_real_entry(homes, monkeypatch, enabled)
    updater = homes.hass.data[DOMAIN][enabled.entry_id]["hourly_updater"]
    assert updater.interval == timedelta(minutes=60) and updater._unsubscribers
    monkeypatch.setattr(
        homes.hass.config_entries,
        "async_unload_platforms",
        AsyncMock(return_value=True),
    )
    await homes.hass.data[DOMAIN][enabled.entry_id]["coordinator"].async_shutdown()
    assert await async_unload_entry(homes.hass, enabled)
    assert updater._closed and not updater._unsubscribers


async def test_options_flow_stores_opt_in_hourly_statistics(ha_hass, ha_entry_factory):
    flow = IntuisOptionsFlow(ha_entry_factory())
    flow.hass = ha_hass
    form = await flow.async_step_energy()
    defaults = {str(key): key.default() for key in form["data_schema"].schema}
    assert defaults[CONF_HOURLY_STATISTICS] is False
    assert defaults[CONF_HOURLY_STATISTICS_INTERVAL] == "120"
    await flow.async_step_energy(
        {CONF_HOURLY_STATISTICS: True, CONF_HOURLY_STATISTICS_INTERVAL: "240"}
    )
    result = await flow.async_step_rate_limit({})
    assert result["data"][CONF_HOURLY_STATISTICS] is True
    assert result["data"][CONF_HOURLY_STATISTICS_INTERVAL] == 240


@pytest.mark.parametrize(
    "value,expected",
    [("1hour", "hourly"), ("hourly", "hourly"), ("1day", "daily"), (None, "daily")],
)
async def test_service_granularity_aliases(
    homes, monkeypatch, frozen_clock, value, expected
):
    frozen_clock.move_to("2026-10-26 10:14:00")
    manager = SimpleNamespace(start=Mock(return_value=True))
    monkeypatch.setattr(
        "custom_components.intuis_connect.services.async_get_import_manager",
        AsyncMock(return_value=manager),
    )
    extra = {} if value is None else {"granularity": value}
    await call(homes, "import_energy_history", home_id="second", days=2, **extra)
    kwargs = manager.start.call_args.kwargs
    if expected == "hourly":
        end = int(datetime(2026, 10, 26, 9, tzinfo=timezone.utc).timestamp())
        assert kwargs == {
            "granularity": "hourly",
            "start": end - 2 * 86400,
            "end": end,
            "room_filter": None,
            "home_id": "second",
            "cost_options": None,
        }
    else:
        assert kwargs == {"days": 2, "room_filter": None, "home_id": "second"}


async def test_service_rejects_unknown_granularity(homes, monkeypatch):
    getter = AsyncMock()
    monkeypatch.setattr(
        "custom_components.intuis_connect.services.async_get_import_manager", getter
    )
    with pytest.raises(vol.Invalid):
        await call(homes, "import_energy_history", days=2, granularity="5min")
    getter.assert_not_awaited()


def blocking_fetch(responses):
    """Hourly fetch that waits for its release; records each started call."""
    started, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def fetch(room_id, start, end):
        calls.append((room_id, start, end))
        started.set()
        await release.wait()
        return responses[room_id]

    return SimpleNamespace(
        api=SimpleNamespace(async_get_room_energy_hourly=fetch),
        started=started,
        release=release,
        calls=calls,
    )


def one_room_home(home_id, name="Living"):
    return SimpleNamespace(
        id=home_id, name=home_id, rooms={"a": SimpleNamespace(name=name)}
    )


def register(ha_hass, entry, manager):
    domain = ha_hass.data.setdefault(DOMAIN, {})
    domain[entry.entry_id] = {}
    domain.setdefault("import_managers", {})[entry.entry_id] = manager


async def test_updater_waits_for_concurrent_manual_import(
    ha_hass, ha_entry_factory, live_recorder, monkeypatch, frozen_clock
):
    frozen_clock.move_to(hour(3) + timedelta(minutes=20))
    monkeypatch.setattr(
        "custom_components.intuis_connect.history_import.API_DELAY_SECONDS", 0
    )
    entry = ha_entry_factory(home_id="home")
    home = one_room_home("home")
    manager = HistoryImportManager(ha_hass, entry.entry_id)
    register(ha_hass, entry, manager)
    fetch = blocking_fetch({"a": wh(0, (1, 2))})
    assert manager.start(fetch.api, home, granularity="hourly", start=ts(0), end=ts(2))
    await fetch.started.wait()
    updater = HourlyStatisticsUpdater(ha_hass, entry, fetch.api, home, 60)
    assert not await updater.async_update()  # deferred, never interleaved
    fetch.release.set()
    await manager._task
    assert [r[2] for r in await series(live_recorder, statistic_id("home", "a"))] == [
        0.001,
        0.003,
    ]
    fetch.started.clear()
    fetch.release.clear()
    assert await updater.async_update()
    await fetch.started.wait()
    # Data is recent, so the updater re-reads the full 48 closed hours.
    assert fetch.calls[-1] == ("a", ts(3) - 48 * H, ts(3))
    fetch.release.set()
    await manager._task


async def test_unloading_one_home_cancels_fetch_while_other_home_continues(
    ha_hass, ha_entry_factory, live_recorder, monkeypatch
):
    monkeypatch.setattr(
        ha_hass.config_entries, "async_unload_platforms", AsyncMock(return_value=True)
    )
    homes_ = {}
    for home_id in ("one", "two"):
        entry = ha_entry_factory(home_id=home_id)
        manager = HistoryImportManager(ha_hass, entry.entry_id)
        register(ha_hass, entry, manager)
        fetch = blocking_fetch({"a": wh(0, (1,))})
        assert manager.start(
            fetch.api,
            one_room_home(home_id),
            granularity="hourly",
            start=ts(0),
            end=ts(1),
        )
        await fetch.started.wait()
        homes_[home_id] = SimpleNamespace(entry=entry, manager=manager, fetch=fetch)
    one, two = homes_["one"], homes_["two"]
    assert await async_unload_entry(ha_hass, one.entry)
    assert one.manager.status == "cancelled" and not one.manager.is_running
    one.fetch.release.set()
    two.fetch.release.set()
    await two.manager._task
    assert two.manager.status == "completed"
    assert await series(live_recorder, statistic_id("two", "a"))
    # The unloaded home wrote nothing and cannot start again.
    assert await series(live_recorder, statistic_id("one", "a")) is None
    assert not one.manager.start(
        one.fetch.api,
        one_room_home("one"),
        granularity="hourly",
        start=ts(0),
        end=ts(1),
    )


async def test_close_during_insert_drains_and_rolls_back(
    ha_hass, live_recorder, monkeypatch
):
    import threading

    from sqlalchemy import event

    api, home, manager = await importer(ha_hass, monkeypatch, [wh(0, (1,))])
    home.rooms = {"a": home.rooms["a"]}
    entered, release = threading.Event(), threading.Event()

    def block_insert(conn, cursor, statement, parameters, context, many):
        if statement.startswith("INSERT INTO statistics ") and not entered.is_set():
            entered.set()
            release.wait(10)

    event.listen(live_recorder.engine, "before_cursor_execute", block_insert)
    try:
        assert manager.start(api, home, granularity="hourly", start=ts(0), end=ts(1))
        loop = asyncio.get_running_loop()
        assert await loop.run_in_executor(None, entered.wait, 10)
        closing = asyncio.create_task(manager.async_close())
        await asyncio.sleep(0.05)
        assert not closing.done()  # unload waits for the recorder acknowledgement
        release.set()
        await asyncio.wait_for(closing, 10)
    finally:
        release.set()
        event.remove(live_recorder.engine, "before_cursor_execute", block_insert)
    assert manager.status == "cancelled"
    # Rolled back as a whole, including the metadata row created in the transaction.
    assert await series(live_recorder, statistic_id("home", "a")) is None


async def test_close_during_store_load_drains_without_starting(
    ha_hass, ha_entry_factory, monkeypatch
):
    from homeassistant.helpers.storage import Store

    entered, release = asyncio.Event(), asyncio.Event()
    original = Store.async_load

    async def blocked_load(self):
        entered.set()
        await release.wait()
        return await original(self)

    monkeypatch.setattr(Store, "async_load", blocked_load)
    window = AsyncMock(return_value=(0, 3600))
    monkeypatch.setattr(
        "custom_components.intuis_connect.hourly_stats.async_update_window", window
    )
    entry = ha_entry_factory(home_id="home")
    ha_hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {}
    api = SimpleNamespace(async_get_room_energy_hourly=AsyncMock())
    updater = HourlyStatisticsUpdater(ha_hass, entry, api, one_room_home("home"), 60)
    updater._schedule()
    await entered.wait()
    closing = asyncio.create_task(updater.async_close())
    await asyncio.sleep(0.05)
    assert not closing.done()  # the executor-backed load is not detached
    release.set()
    await asyncio.wait_for(closing, 10)
    window.assert_not_awaited()
    api.async_get_room_energy_hourly.assert_not_awaited()


async def test_restart_resumes_from_recorder_without_auxiliary_storage(
    ha_hass, ha_entry_factory, live_recorder, monkeypatch, frozen_clock
):
    from homeassistant.helpers.storage import Store

    saves = []
    monkeypatch.setattr(Store, "async_save", AsyncMock(side_effect=saves.append))
    api, home, manager = await importer(ha_hass, monkeypatch, [wh(0, (1000, 1000))])
    home.rooms = {"a": home.rooms["a"]}
    await run(ha_hass, api, home, manager, 0, 2)
    assert not saves  # hourly progress is the recorder itself
    # A restart: fresh managers and no in-memory state, only the recorder rows.
    ha_hass.data.pop(DOMAIN, None)
    frozen_clock.move_to(hour(60) + timedelta(minutes=20))
    entry = ha_entry_factory(home_id="home")
    ha_hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {}
    api.async_get_room_energy_hourly = AsyncMock(return_value=wh(2, (1000,) * 58))
    updater = HourlyStatisticsUpdater(ha_hass, entry, api, home, 60)
    assert await updater.async_update()
    task = ha_hass.data[DOMAIN]["import_managers"][entry.entry_id]._task
    await task
    api.async_get_room_energy_hourly.assert_awaited_once_with("a", ts(2), ts(60))
    rows = await series(live_recorder, statistic_id("home", "a"))
    assert len(rows) == 60 and rows[-1][2] == 60 and not saves


async def test_room_rename_keeps_one_continuous_series(
    ha_hass, live_recorder, monkeypatch
):
    api, home, manager = await importer(
        ha_hass, monkeypatch, [wh(0, (1000, 1000)), wh(2, (500,))]
    )
    home.rooms = {"a": SimpleNamespace(name="Living")}
    await run(ha_hass, api, home, manager, 0, 2)
    home.rooms["a"].name = "Lounge"
    await run(ha_hass, api, home, manager, 2, 1)
    rows = await series(live_recorder, statistic_id("home", "a"))
    assert [r[2] for r in rows] == [1, 2, 2.5]

    def names():
        from homeassistant.components.recorder.db_schema import StatisticsMeta
        from sqlalchemy import select

        with live_recorder.get_session() as session:
            return list(session.scalars(select(StatisticsMeta.name)))

    # One identity; the label from creation is kept (no metadata churn).
    assert await live_recorder.async_add_executor_job(names) == [
        "Living hourly energy",
        "House hourly energy",
    ]
