"""Community #22 cost schemas stay untouched and never collide with new costs."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.intuis_connect import sensor
from custom_components.intuis_connect.external_statistics import statistic_id
from custom_components.intuis_connect.hourly_stats import entry_cost_options
from custom_components.intuis_connect.sensor import IntuisCostSensor
from custom_components.intuis_connect.utils.const import (
    CONF_HOURLY_STATISTICS,
    DOMAIN,
)

from .test_cost_series import FIXED, job
from .test_history_import import live_recorder as _live_recorder
from .test_hourly_statistics import series
from .test_hourly_updater import wh


@pytest.fixture
async def live_recorder(ha_hass, tmp_path):
    async for instance in _live_recorder.__wrapped__(ha_hass, tmp_path):
        yield instance


# Options written by TheFab21's #22/#24 builds (inventoried in docs/12).
COMMUNITY_OPTIONS = {
    "energy_cost_enabled": True,
    "energy_price_mode": "fixed",
    "energy_fixed_price": 0.25,
    "energy_price_entity": "",
}


async def registries(ha_hass):
    if hasattr(dr, "async_setup"):
        dr.async_setup(ha_hass)
    await dr.async_load(ha_hass)
    registry = er.async_get(ha_hass)
    await registry.async_load()
    return registry


async def cost_displays(ha_hass, ha_entry_factory, monkeypatch, rooms, options):
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
        monkeypatch.setattr(sensor, name, lambda *a, **kw: None)
    monkeypatch.setattr(sensor, "provide_home_sensors", lambda *a: [])
    entry = ha_entry_factory(options=options)
    ha_hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"intuis_home": None}
    added = []
    await sensor.async_setup_entry(
        ha_hass, entry, lambda items, **kw: added.extend(items)
    )
    return entry, [e for e in added if isinstance(e, IntuisCostSensor)]


async def test_community_options_neither_enable_costs_nor_get_removed(
    ha_hass, ha_entry_factory, monkeypatch
):
    rooms = {"a": SimpleNamespace(id="a", name="Living", modules=[])}
    entry, displays = await cost_displays(
        ha_hass, ha_entry_factory, monkeypatch, rooms, COMMUNITY_OPTIONS
    )
    assert entry_cost_options(entry.options) is None and not displays
    assert dict(entry.options) == COMMUNITY_OPTIONS


async def test_new_displays_never_take_or_remove_existing_entities(
    ha_hass, ha_entry_factory, monkeypatch
):
    registry = await registries(ha_hass)
    # #22 cost entities of this domain and the energy dashboard's own cost entity.
    community = [
        registry.async_get_or_create(
            "sensor", DOMAIN, f"intuis_home_a_{suffix}", suggested_object_id=object_id
        )
        for suffix, object_id in (
            ("cost", "sejour_cost"),
            ("energy_cost", "sejour_energy_cost"),
        )
    ]
    foreign = registry.async_get_or_create(
        "sensor", "energy", "dashboard_cost", suggested_object_id="sejour_hourly_cost"
    )
    rooms = {"a": SimpleNamespace(id="a", name="Séjour", modules=[])}
    _, displays = await cost_displays(
        ha_hass,
        ha_entry_factory,
        monkeypatch,
        rooms,
        {CONF_HOURLY_STATISTICS: True, **FIXED},
    )
    created = {
        e.unique_id: registry.async_get_or_create(
            "sensor", DOMAIN, e.unique_id, suggested_object_id=e.name
        )
        for e in displays
    }
    room = created["intuis_home_a_hourly_cost"]
    # The occupied object ID is not taken over: a distinct ID is obtained.
    assert room.entity_id == "sensor.sejour_hourly_cost_2"
    assert registry.async_get(foreign.entity_id).platform == "energy"
    for old in community:
        assert registry.async_get(old.entity_id).unique_id == old.unique_id
    assert {e.unique_id for e in displays}.isdisjoint(c.unique_id for c in community)

    # Renaming the room keeps the same registry entry and statistics identity.
    rooms["a"].name = "Salon"
    _, renamed = await cost_displays(
        ha_hass,
        ha_entry_factory,
        monkeypatch,
        rooms,
        {CONF_HOURLY_STATISTICS: True, **FIXED},
    )
    again = registry.async_get_or_create(
        "sensor", DOMAIN, renamed[0].unique_id, suggested_object_id=renamed[0].name
    )
    assert again.id == room.id and again.entity_id == room.entity_id


async def test_community_recorder_cost_statistics_are_left_intact(
    ha_hass, live_recorder, monkeypatch
):
    from homeassistant.components.recorder.db_schema import Statistics, StatisticsMeta

    ha_hass.config.currency = "EUR"

    def seed():
        with live_recorder.get_session() as session, session.begin():
            meta = StatisticsMeta(
                statistic_id="sensor.sejour_cost",
                source="recorder",
                unit_of_measurement="EUR",
                has_sum=True,
                has_mean=False,
            )
            session.add(meta)
            session.flush()
            session.add(Statistics(metadata_id=meta.id, start_ts=0, state=1, sum=1))

    await live_recorder.async_add_executor_job(seed)
    before = await series(live_recorder, "sensor.sejour_cost")
    await job(
        ha_hass, monkeypatch, [wh(0, (1000, 0)), wh(0, (0, 0))], cost_options=FIXED
    )
    assert await series(live_recorder, "sensor.sejour_cost") == before
    new_ids = {statistic_id("home", room, "cost") for room in ("a", "b", None)}
    assert all(sid.startswith("intuis_connect:cost_") for sid in new_ids)
    assert "sensor.sejour_cost" not in new_ids


@pytest.mark.parametrize("name", ["Séjour", "Chambre d’amis", "Salle de bain 2"])
def test_accented_names_do_not_change_identities(name):
    display = IntuisCostSensor("entry", "home", "a", name, "EUR")
    assert display.unique_id == "intuis_home_a_hourly_cost"
    assert name not in statistic_id("home", "a", "cost")
    assert display.name == f"{name} Hourly Cost"
