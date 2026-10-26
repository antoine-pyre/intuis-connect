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
