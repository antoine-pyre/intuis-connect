"""Price and cost contract adapted from TheFab21's #22/#24 cost proposal."""

from datetime import datetime, timedelta, timezone

import pytest

from custom_components.intuis_connect.cost_stats import (
    CostPriceError,
    fixed_prices,
    hourly_costs,
    parse_price,
    price_unit_matches,
    prices_at_hours,
)

H = 3600
T0 = int(datetime(2026, 10, 25, tzinfo=timezone.utc).timestamp())


@pytest.mark.parametrize(
    "value,expected",
    [
        ("0.25", 0.25),
        (-0.05, -0.05),
        (0, 0.0),
        ("unavailable", None),
        ("unknown", None),
        (None, None),
        (True, None),
        ("nan", None),
        (float("inf"), None),
    ],
)
def test_prices_are_finite_and_may_be_negative(value, expected):
    assert parse_price(value) == expected


@pytest.mark.parametrize(
    "unit,currency,ok",
    [
        ("EUR/kWh", "EUR", True),
        ("€/kWh", "EUR", True),
        ("€ / kWh", "EUR", True),
        ("EUR/Wh", "EUR", False),
        ("EUR/MWh", "EUR", False),
        ("USD/kWh", "EUR", False),
        ("€/kWh", "USD", False),
        (None, "EUR", False),
    ],
)
def test_price_unit_must_match_currency_per_kwh(unit, currency, ok):
    assert price_unit_matches(unit, currency) is ok


def test_price_in_force_at_each_hour_start():
    changes = [(T0 - 600, "0.20"), (T0 + 1800, "0.30"), (T0 + H, "-0.01")]
    # The 00:30 change applies from 01:00; a change exactly on the hour applies to it.
    assert prices_at_hours(changes, [T0, T0 + H, T0 + 2 * H]) == (0.2, -0.01, -0.01)


@pytest.mark.parametrize(
    "changes",
    [
        [],
        [(T0 + 1, "0.2")],
        [(T0 - 1, "0.2"), (T0 + H, "unavailable")],
        [(T0 - 1, "abc")],
    ],
)
def test_price_gaps_refuse_the_period(changes):
    with pytest.raises(CostPriceError, match="No valid price"):
        prices_at_hours(changes, [T0, T0 + H])


def test_fixed_price_applies_only_to_requested_hours():
    assert fixed_prices("0.2516", [T0, T0 + H]) == (0.2516, 0.2516)
    with pytest.raises(CostPriceError):
        fixed_prices("", [T0])


def test_hourly_costs_are_unrounded_and_require_contiguous_hours():
    start = datetime.fromtimestamp(T0, timezone.utc)
    energy = [(start, 0.333), (start + timedelta(hours=1), 0)]
    assert hourly_costs(energy, (0.2516, 0.3)) == (
        (start, 0.333 * 0.2516),
        (energy[1][0], 0),
    )
    for bad in (
        [(start, 1), (start + timedelta(hours=2), 1)],
        [(start, -1), (start + timedelta(hours=1), 1)],
        [(start + timedelta(minutes=5), 1), (start + timedelta(hours=1), 1)],
    ):
        with pytest.raises(CostPriceError):
            hourly_costs(bad, (0.2, 0.2))
    with pytest.raises(CostPriceError):
        hourly_costs(energy, (0.2,))


# ---- Options and recorded price history (task 1.2) -------------------------

from homeassistant.helpers import selector  # noqa: E402

from custom_components.intuis_connect.config_flow import IntuisOptionsFlow  # noqa: E402
from custom_components.intuis_connect.cost_stats import async_hour_prices  # noqa: E402
from custom_components.intuis_connect.utils.const import (  # noqa: E402
    CONF_COST_FIXED_PRICE,
    CONF_COST_PRICE_ENTITY,
    CONF_COST_PRICE_MODE,
    CONF_COST_STATISTICS,
    CONF_HOURLY_STATISTICS,
)

from .test_history_import import live_recorder as _live_recorder  # noqa: E402


@pytest.fixture
async def live_recorder(ha_hass, tmp_path):
    async for instance in _live_recorder.__wrapped__(ha_hass, tmp_path):
        yield instance


async def cost_form(ha_hass, ha_entry_factory, hourly=True, options=None):
    flow = IntuisOptionsFlow(ha_entry_factory(options=options or {}))
    flow.hass = ha_hass
    flow._override_options = {CONF_HOURLY_STATISTICS: hourly}
    return flow, await flow.async_step_cost()


async def test_cost_selectors_are_valid_on_this_ha_version(ha_hass, ha_entry_factory):
    _, form = await cost_form(ha_hass, ha_entry_factory)
    fields = {
        str(key): (key, value) for key, value in form["data_schema"].schema.items()
    }
    assert fields[CONF_COST_STATISTICS][0].default() is False
    assert fields[CONF_COST_PRICE_MODE][1]("entity") == "entity"
    number = fields[CONF_COST_FIXED_PRICE][1]
    assert number(-0.05) == -0.05 and number(0.2516) == 0.2516
    assert fields[CONF_COST_PRICE_ENTITY][1]("sensor.price") == "sensor.price"
    # 0.25 is only a suggestion shown in the form, not a default value.
    key = fields[CONF_COST_FIXED_PRICE][0]
    assert key.description == {"suggested_value": 0.25}
    assert key.default is vol.UNDEFINED
    assert isinstance(fields[CONF_COST_PRICE_MODE][1], selector.SelectSelector)


import voluptuous as vol  # noqa: E402


@pytest.mark.parametrize(
    "user_input,hourly,state,error",
    [
        (
            {CONF_COST_STATISTICS: True, CONF_COST_PRICE_MODE: "fixed"},
            True,
            None,
            (CONF_COST_FIXED_PRICE, "fixed_price_required"),
        ),
        (
            {
                CONF_COST_STATISTICS: True,
                CONF_COST_PRICE_MODE: "fixed",
                CONF_COST_FIXED_PRICE: 0.2,
            },
            False,
            None,
            (CONF_COST_STATISTICS, "cost_requires_hourly"),
        ),
        (
            {
                CONF_COST_STATISTICS: True,
                CONF_COST_PRICE_MODE: "entity",
                CONF_COST_PRICE_ENTITY: "sensor.p",
            },
            True,
            None,
            (CONF_COST_PRICE_ENTITY, "price_entity_not_found"),
        ),
        (
            {
                CONF_COST_STATISTICS: True,
                CONF_COST_PRICE_MODE: "entity",
                CONF_COST_PRICE_ENTITY: "sensor.p",
            },
            True,
            "EUR/MWh",
            (CONF_COST_PRICE_ENTITY, "price_entity_unit"),
        ),
    ],
)
async def test_invalid_cost_options_show_errors(
    ha_hass, ha_entry_factory, user_input, hourly, state, error
):
    if state:
        ha_hass.states.async_set("sensor.p", "0.2", {"unit_of_measurement": state})
    flow, _ = await cost_form(ha_hass, ha_entry_factory, hourly)
    result = await flow.async_step_cost(user_input)
    assert result["type"] == "form" and result["errors"] == {error[0]: error[1]}
    assert CONF_COST_STATISTICS not in flow._override_options


@pytest.mark.parametrize(
    "user_input",
    [
        {CONF_COST_STATISTICS: False},
        {
            CONF_COST_STATISTICS: True,
            CONF_COST_PRICE_MODE: "fixed",
            CONF_COST_FIXED_PRICE: -0.01,
        },
        {
            CONF_COST_STATISTICS: True,
            CONF_COST_PRICE_MODE: "entity",
            CONF_COST_PRICE_ENTITY: "sensor.p",
        },
    ],
)
async def test_valid_cost_options_are_stored(ha_hass, ha_entry_factory, user_input):
    ha_hass.states.async_set("sensor.p", "0.2", {"unit_of_measurement": "€/kWh"})
    flow, _ = await cost_form(ha_hass, ha_entry_factory)
    result = await flow.async_step_cost(user_input)
    assert result["step_id"] == "rate_limit"
    data = (await flow.async_step_rate_limit({}))["data"]
    for key, value in user_input.items():
        assert data[key] == value
    assert data[CONF_HOURLY_STATISTICS] is True


async def record(ha_hass, recorder, clock, when, state, unit="EUR/kWh"):
    from homeassistant.components.recorder.tasks import CommitTask

    clock.move_to(datetime.fromtimestamp(when, timezone.utc))
    ha_hass.states.async_set(
        "sensor.price", state, {"unit_of_measurement": unit}, force_update=True
    )
    await ha_hass.async_block_till_done()
    recorder.queue_task(CommitTask())
    await recorder.async_block_till_done()


async def test_recorded_price_history_is_read_per_hour(
    ha_hass, live_recorder, frozen_clock
):
    # HA 2024.6 only returns the state in force at a period start when a
    # recorder run covered that time; its run starts on the unfrozen clock.
    ha_hass.config.currency = "EUR"
    run_start = live_recorder.recorder_runs_manager.recording_start.timestamp()
    b = (int(run_start) // H + 3) * H
    await record(ha_hass, live_recorder, frozen_clock, b - H - 600, "0.20")
    await record(ha_hass, live_recorder, frozen_clock, b + 1800, "0.30")
    await record(ha_hass, live_recorder, frozen_clock, b + 2 * H, "0.10", "EUR/MWh")
    await record(ha_hass, live_recorder, frozen_clock, b + 3 * H, "-0.02")
    frozen_clock.move_to(datetime.fromtimestamp(b + 5 * H, timezone.utc))
    options = {CONF_COST_PRICE_MODE: "entity", CONF_COST_PRICE_ENTITY: "sensor.price"}
    # The state recorded before the window is in force at its start; a change
    # exactly on the hour applies to that hour.
    assert await async_hour_prices(ha_hass, options, "EUR", [b, b + H]) == (0.2, 0.3)
    assert await async_hour_prices(ha_hass, options, "EUR", [b + 3 * H]) == (-0.02,)
    # A recorded value in another unit is a gap, not a conversion.
    with pytest.raises(CostPriceError, match="No valid price"):
        await async_hour_prices(ha_hass, options, "EUR", [b + H, b + 2 * H])
    # Before any recorded state there is no price to apply.
    with pytest.raises(CostPriceError):
        await async_hour_prices(ha_hass, options, "EUR", [b - 2 * H])


async def test_fixed_and_missing_price_sources(ha_hass):
    fixed = {CONF_COST_PRICE_MODE: "fixed", CONF_COST_FIXED_PRICE: 0.25}
    assert await async_hour_prices(ha_hass, fixed, "EUR", [T0, T0 + H]) == (0.25, 0.25)
    with pytest.raises(CostPriceError, match="No price source"):
        await async_hour_prices(ha_hass, {CONF_COST_PRICE_MODE: "entity"}, "EUR", [T0])
    assert await async_hour_prices(ha_hass, fixed, "EUR", []) == ()
