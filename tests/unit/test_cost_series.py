"""Cost series written with confirmed hourly kWh (adapted from TheFab21 #22/#24)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from custom_components.intuis_connect.cost_stats import cost_signal
from custom_components.intuis_connect.external_statistics import statistic_id
from custom_components.intuis_connect.history_import import HistoryImportManager
from custom_components.intuis_connect.hourly_stats import async_import_hourly_history
from custom_components.intuis_connect.sensor import IntuisCostSensor
from custom_components.intuis_connect.utils.const import (
    CONF_COST_FIXED_PRICE,
    CONF_COST_PRICE_ENTITY,
    CONF_COST_PRICE_MODE,
    CONF_COST_STATISTICS,
)

from .test_history_import import live_recorder as _live_recorder
from .test_hourly_statistics import series
from .test_hourly_updater import ts, wh

FIXED = {
    CONF_COST_STATISTICS: True,
    CONF_COST_PRICE_MODE: "fixed",
    CONF_COST_FIXED_PRICE: 0.2,
}


@pytest.fixture
async def live_recorder(ha_hass, tmp_path):
    async for instance in _live_recorder.__wrapped__(ha_hass, tmp_path):
        yield instance


async def job(
    ha_hass,
    monkeypatch,
    responses,
    *,
    home_id="home",
    entry_id="entry",
    end_hour=2,
    **kwargs,
):
    monkeypatch.setattr(
        "custom_components.intuis_connect.history_import.API_DELAY_SECONDS", 0
    )
    api = SimpleNamespace(async_get_room_energy_hourly=AsyncMock(side_effect=responses))
    home = SimpleNamespace(
        id=home_id,
        name="House",
        rooms={"a": SimpleNamespace(name="Living"), "b": SimpleNamespace(name="Bed")},
    )
    manager = HistoryImportManager(ha_hass, entry_id)
    await manager.async_load()
    published = []
    async_dispatcher_connect(
        ha_hass, cost_signal(entry_id), lambda: published.append(1)
    )
    result = await async_import_hourly_history(
        ha_hass, api, home, manager, start=ts(0), end=ts(end_hour), **kwargs
    )
    await ha_hass.async_block_till_done()
    return result, manager, published


def costs(rows):
    return [(round(r[1], 6), round(r[2], 6)) for r in rows]


async def test_room_and_home_costs_follow_confirmed_kwh(
    ha_hass, live_recorder, monkeypatch
):
    ha_hass.config.currency = "EUR"
    result, manager, published = await job(
        ha_hass, monkeypatch, [wh(0, (1000, 500)), wh(0, (0, 2000))], cost_options=FIXED
    )
    assert result["costs"] == "complete" and result["status"] == "completed"
    assert costs(await series(live_recorder, statistic_id("home", "a", "cost"))) == [
        (0.2, 0.2),
        (0.1, 0.3),
    ]
    assert costs(await series(live_recorder, statistic_id("home", None, "cost"))) == [
        (0.2, 0.2),
        (0.5, 0.7),
    ]
    # Energy is identical to an import without costs.
    assert [r[1] for r in await series(live_recorder, statistic_id("home", "a"))] == [
        1,
        0.5,
    ]
    assert published == [1] and manager.cost_status == "complete"


async def test_negative_tariff_produces_negative_cost(
    ha_hass, live_recorder, monkeypatch
):
    options = {**FIXED, CONF_COST_FIXED_PRICE: -0.05}
    await job(
        ha_hass, monkeypatch, [wh(0, (1000, 0)), wh(0, (0, 0))], cost_options=options
    )
    assert costs(await series(live_recorder, statistic_id("home", "a", "cost"))) == [
        (-0.05, -0.05),
        (0, -0.05),
    ]


async def test_price_gap_keeps_energy_and_writes_no_cost(
    ha_hass, live_recorder, monkeypatch
):
    options = {
        CONF_COST_STATISTICS: True,
        CONF_COST_PRICE_MODE: "entity",
        CONF_COST_PRICE_ENTITY: "sensor.none",
    }
    result, manager, published = await job(
        ha_hass, monkeypatch, [wh(0, (1000, 0)), wh(0, (0, 0))], cost_options=options
    )
    assert result["status"] == "completed" and result["costs"] == "failed"
    assert "No valid price" in manager.last_error
    assert await series(live_recorder, statistic_id("home", "a")) is not None
    assert await series(live_recorder, statistic_id("home", "a", "cost")) is None
    assert not published


async def test_currency_change_is_refused_and_preserves_costs(
    ha_hass, live_recorder, monkeypatch
):
    ha_hass.config.currency = "EUR"
    await job(
        ha_hass, monkeypatch, [wh(0, (1000, 0)), wh(0, (0, 0))], cost_options=FIXED
    )
    before = await series(live_recorder, statistic_id("home", "a", "cost"))
    ha_hass.config.currency = "USD"
    result, manager, _ = await job(
        ha_hass, monkeypatch, [wh(0, (3000, 0)), wh(0, (0, 0))], cost_options=FIXED
    )
    assert result["costs"] == "failed" and "incompatible" in manager.last_error
    assert await series(live_recorder, statistic_id("home", "a", "cost")) == before
    # The confirmed energy was still replaced.
    assert [r[1] for r in await series(live_recorder, statistic_id("home", "a"))] == [
        3,
        0,
    ]


async def test_costs_disabled_write_nothing(ha_hass, live_recorder, monkeypatch):
    result, manager, published = await job(
        ha_hass, monkeypatch, [wh(0, (1000, 0)), wh(0, (0, 0))]
    )
    assert result["costs"] == "disabled" and not published
    assert await series(live_recorder, statistic_id("home", "a", "cost")) is None


async def test_display_sensor_is_not_a_second_writer_and_isolated_per_entry(
    ha_hass, live_recorder, monkeypatch
):
    from unittest.mock import Mock

    from homeassistant.components.recorder import statistics

    ha_hass.config.currency = "EUR"
    mine = IntuisCostSensor("entry", "home", "a", "Living", "EUR")
    other = IntuisCostSensor("other", "other", "a", "Living", "EUR")
    assert mine.state_class is None and mine.unique_id == "intuis_home_a_hourly_cost"
    assert mine.native_unit_of_measurement == "EUR"
    for sensor, entity_id in (
        (mine, "sensor.living_cost"),
        (other, "sensor.other_cost"),
    ):
        # HA's state machine write is HA's concern; observe what we publish.
        sensor.hass, sensor.entity_id = ha_hass, entity_id
        sensor.async_write_ha_state = Mock()
        await sensor.async_added_to_hass()
    assert mine.native_value is None
    await job(
        ha_hass, monkeypatch, [wh(0, (1000, 500)), wh(0, (0, 0))], cost_options=FIXED
    )
    await ha_hass.async_block_till_done()
    assert mine.native_value == pytest.approx(0.3)
    assert mine.extra_state_attributes["last_hour_end"].startswith("2026-10-25T02:00")
    assert mine.async_write_ha_state.call_count == 2
    # Another home's sensor is not refreshed by this entry's signal.
    assert other.native_value is None and other.async_write_ha_state.call_count == 1
    # The display entity has no statistics of its own.
    ids = {
        row["statistic_id"]
        for row in await live_recorder.async_add_executor_job(
            statistics.list_statistic_ids, ha_hass
        )
    }
    assert "sensor.living_cost" not in ids and statistic_id("home", "a", "cost") in ids


@pytest.mark.parametrize("enabled", [False, True])
async def test_platform_adds_cost_displays_only_when_enabled(
    ha_hass, ha_entry_factory, monkeypatch, enabled
):
    from custom_components.intuis_connect import sensor

    rooms = {"a": SimpleNamespace(id="a", name="Living", modules=[])}
    monkeypatch.setattr(
        sensor, "get_basic_utils", lambda hass, entry: ("coord", "home", rooms, "api")
    )
    for name in (
        "IntuisTemperatureSensor",
        "IntuisMullerTypeSensor",
        "IntuisEnergySensor",
        "IntuisMinutesSensor",
        "IntuisSetpointEndTimeSensor",
        "IntuisScheduledTempSensor",
    ):
        monkeypatch.setattr(sensor, name, lambda *a, **kw: "room-sensor")
    monkeypatch.setattr(sensor, "provide_home_sensors", lambda *a: [])
    entry = ha_entry_factory(options={CONF_COST_STATISTICS: enabled})
    ha_hass.data.setdefault("intuis_connect", {})[entry.entry_id] = {
        "intuis_home": None
    }
    ha_hass.config.currency = "CHF"
    added = []
    await sensor.async_setup_entry(
        ha_hass, entry, lambda items, **kw: added.extend(items)
    )
    displays = [e for e in added if isinstance(e, IntuisCostSensor)]
    if not enabled:
        assert not displays
    else:
        assert sorted(e.unique_id for e in displays) == [
            "intuis_home_a_hourly_cost",
            "intuis_home_home_hourly_cost",
        ]
        assert {e.native_unit_of_measurement for e in displays} == {"CHF"}


# ---- recalculate_cost_history through the real service (task 2.2) ----------

from homeassistant.exceptions import HomeAssistantError, ServiceValidationError  # noqa: E402

from custom_components.intuis_connect.history_import import (  # noqa: E402
    async_get_import_manager,
)
from custom_components.intuis_connect.services import async_register_services  # noqa: E402
from custom_components.intuis_connect.utils.const import DOMAIN  # noqa: E402


async def service_home(
    ha_hass, ha_entry_factory, monkeypatch, frozen_clock, *, cost=FIXED
):
    """One loaded home with 24 confirmed hours of energy for rooms a and b."""
    frozen_clock.move_to("2026-10-26 00:20:00")
    ha_hass.config.currency = "EUR"
    result, _, _ = await job(
        ha_hass,
        monkeypatch,
        [wh(0, [1000] * 24), wh(0, [500] * 24)],
        end_hour=24,
    )
    assert result["status"] == "completed"
    entry = ha_entry_factory(home_id="home")
    home = SimpleNamespace(
        id="home",
        name="House",
        rooms={"a": SimpleNamespace(name="Living"), "b": SimpleNamespace(name="Bed")},
    )
    ha_hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "intuis_home": home,
        "api": SimpleNamespace(),
        "options": dict(cost or {}),
    }
    await async_register_services(ha_hass, entry)
    return entry


async def recalc(ha_hass, **data):
    return await ha_hass.services.async_call(
        DOMAIN, "recalculate_cost_history", data, blocking=True, return_response=True
    )


async def test_service_recalculates_from_confirmed_energy_and_is_idempotent(
    ha_hass, ha_entry_factory, live_recorder, monkeypatch, frozen_clock
):
    await service_home(ha_hass, ha_entry_factory, monkeypatch, frozen_clock)
    energy = await series(live_recorder, statistic_id("home", "a"))
    response = await recalc(ha_hass, days=1)
    home = response["homes"]["home"]
    assert home["status"] == "completed" and home["rooms_recalculated"] == 2
    assert home["hours"] == 24 and home["home_total"] == "complete"
    room = await series(live_recorder, statistic_id("home", "a", "cost"))
    assert len(room) == 24 and room[-1][2] == pytest.approx(24 * 0.2)
    total = await series(live_recorder, statistic_id("home", None, "cost"))
    assert total[-1][2] == pytest.approx(24 * 0.3)
    assert await recalc(ha_hass, days=1) == response
    assert await series(live_recorder, statistic_id("home", "a", "cost")) == room
    # Energy statistics are only read.
    assert await series(live_recorder, statistic_id("home", "a")) == energy


async def test_new_price_rewrites_only_the_targeted_room(
    ha_hass, ha_entry_factory, live_recorder, monkeypatch, frozen_clock
):
    entry = await service_home(ha_hass, ha_entry_factory, monkeypatch, frozen_clock)
    await recalc(ha_hass, days=1)
    total = await series(live_recorder, statistic_id("home", None, "cost"))
    bed = await series(live_recorder, statistic_id("home", "b", "cost"))
    ha_hass.data[DOMAIN][entry.entry_id]["options"][CONF_COST_FIXED_PRICE] = 0.5
    response = await recalc(ha_hass, days=1, room_name="living", home_id="home")
    assert response["homes"]["home"]["home_total"] == "skipped"
    living = await series(live_recorder, statistic_id("home", "a", "cost"))
    assert living[-1][2] == pytest.approx(24 * 0.5)
    assert await series(live_recorder, statistic_id("home", "b", "cost")) == bed
    assert await series(live_recorder, statistic_id("home", None, "cost")) == total


async def test_missing_energy_fails_visibly_and_keeps_costs(
    ha_hass, ha_entry_factory, live_recorder, monkeypatch, frozen_clock
):
    await service_home(ha_hass, ha_entry_factory, monkeypatch, frozen_clock)
    await recalc(ha_hass, days=1)
    before = await series(live_recorder, statistic_id("home", "a", "cost"))
    # Two days: the first day has no confirmed energy.
    with pytest.raises(HomeAssistantError, match="No confirmed hourly energy"):
        await recalc(ha_hass, days=2)
    assert await series(live_recorder, statistic_id("home", "a", "cost")) == before


async def test_service_refuses_disabled_costs_and_busy_homes(
    ha_hass, ha_entry_factory, live_recorder, monkeypatch, frozen_clock
):
    entry = await service_home(ha_hass, ha_entry_factory, monkeypatch, frozen_clock)
    manager = await async_get_import_manager(ha_hass, entry.entry_id)
    manager._running = True  # an hourly import holds this home
    with pytest.raises(HomeAssistantError, match="running"):
        await recalc(ha_hass, days=1)
    manager._running = False
    ha_hass.data[DOMAIN][entry.entry_id]["options"] = {}
    with pytest.raises(ServiceValidationError, match="not enabled"):
        await recalc(ha_hass, days=1)
    assert await series(live_recorder, statistic_id("home", "a", "cost")) is None
