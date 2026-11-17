"""Daily rebase of the cumulative energy level.

The hourly series alone is relative, so these contracts are what stop a
missed or revised hour from staying in the sum for good.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from custom_components.intuis_connect.energy_base import (
    MAX_CATCH_UP_DAYS,
    EnergyBase,
    daily_totals,
    local_midnight,
    settled_day,
)

ZONE = ZoneInfo("Europe/Zurich")
NOW = datetime(2026, 11, 17, 9, 30, tzinfo=timezone.utc)


def noon(day: date) -> int:
    """The cloud stamps a day at its local noon."""
    return int(datetime(day.year, day.month, day.day, 12, tzinfo=ZONE).timestamp())


def test_settled_day_leaves_the_cloud_a_full_day() -> None:
    assert settled_day(NOW, ZONE) == date(2026, 11, 15)


def test_settled_day_refuses_a_naive_clock() -> None:
    with pytest.raises(ValueError):
        settled_day(datetime(2026, 11, 17, 9, 30), ZONE)


def test_daily_totals_map_local_noon_to_its_local_day_in_kwh() -> None:
    samples = [(noon(date(2026, 11, 14)), 4200.0), (noon(date(2026, 11, 15)), 3100.0)]
    assert daily_totals(samples, ZONE, date(2026, 11, 14), date(2026, 11, 15)) == {
        date(2026, 11, 14): 4.2,
        date(2026, 11, 15): 3.1,
    }


def test_daily_totals_ignore_days_outside_the_requested_range() -> None:
    samples = [(noon(date(2026, 11, 16)), 9990.0)]
    assert daily_totals(samples, ZONE, date(2026, 11, 14), date(2026, 11, 15)) == {}


def test_daily_totals_refuse_a_duplicate_day() -> None:
    samples = [(noon(date(2026, 11, 14)), 1.0), (noon(date(2026, 11, 14)) + 60, 2.0)]
    with pytest.raises(ValueError):
        daily_totals(samples, ZONE, date(2026, 11, 14), date(2026, 11, 15))


@pytest.mark.parametrize("value", [-1.0, float("nan"), True])
def test_daily_totals_refuse_an_invalid_measurement(value: object) -> None:
    with pytest.raises(ValueError):
        daily_totals(
            [(noon(date(2026, 11, 14)), value)], ZONE, date(2026, 11, 14), date(2026, 11, 15)
        )


def test_an_unseeded_base_asks_to_be_seeded() -> None:
    base = EnergyBase({})
    assert base.needs_reseed(NOW, ZONE) is True
    assert base.settled_through is None
    assert base.level("room") is None
    assert base.hourly_start(ZONE) is None
    assert base.plan(NOW, ZONE) is None


def test_plan_covers_every_day_between_the_level_and_the_settled_day() -> None:
    base = EnergyBase({})
    base.seed(date(2026, 11, 13), {"r1": 100.0})
    plan = base.plan(NOW, ZONE)
    assert (plan.first, plan.last, plan.days) == (
        date(2026, 11, 14),
        date(2026, 11, 15),
        2,
    )
    assert plan.begin == int(local_midnight(date(2026, 11, 14), ZONE).timestamp())
    assert plan.end == int(local_midnight(date(2026, 11, 16), ZONE).timestamp())


def test_advancing_adds_the_days_then_leaves_nothing_to_do() -> None:
    base = EnergyBase({})
    base.seed(date(2026, 11, 13), {"r1": 100.0, "r2": 50.0})
    base.advance(date(2026, 11, 15), {"r1": 7.3, "r2": 1.0})
    assert base.level("r1") == 107.3
    assert base.level("r2") == 51.0
    assert base.settled_through == date(2026, 11, 15)
    assert base.plan(NOW, ZONE) is None


def test_advancing_refuses_an_invalid_total() -> None:
    base = EnergyBase({})
    base.seed(date(2026, 11, 14), {"r1": 1.0})
    with pytest.raises(ValueError):
        base.advance(date(2026, 11, 15), {"r1": -1.0})


def test_the_hourly_window_starts_at_midnight_after_the_level() -> None:
    base = EnergyBase({})
    base.seed(date(2026, 11, 15), {"r1": 1.0})
    assert base.hourly_start(ZONE) == int(
        local_midnight(date(2026, 11, 16), ZONE).timestamp()
    )


def test_a_long_outage_is_reseeded_rather_than_replayed() -> None:
    base = EnergyBase({})
    base.seed(date(2026, 1, 1), {"r1": 1.0})
    assert base.plan(NOW, ZONE) is None
    assert base.needs_reseed(NOW, ZONE) is True


@pytest.mark.parametrize("lag", [1, MAX_CATCH_UP_DAYS - 1, MAX_CATCH_UP_DAYS])
def test_a_lag_within_the_bound_is_still_replayed(lag: int) -> None:
    base = EnergyBase({})
    base.seed(settled_day(NOW, ZONE) - timedelta(days=lag), {"r1": 1.0})
    assert base.needs_reseed(NOW, ZONE) is False
    assert base.plan(NOW, ZONE).days == lag


@pytest.mark.parametrize("lag", [1, MAX_CATCH_UP_DAYS, MAX_CATCH_UP_DAYS + 1, 400])
def test_replaying_and_reseeding_never_leave_a_lag_unhandled(lag: int) -> None:
    """With days to catch up, exactly one of the two paths must apply."""
    base = EnergyBase({})
    base.seed(settled_day(NOW, ZONE) - timedelta(days=lag), {"r1": 1.0})
    replays = base.plan(NOW, ZONE) is not None
    assert replays is not base.needs_reseed(NOW, ZONE)


def test_a_level_already_at_the_settled_day_has_nothing_to_do() -> None:
    base = EnergyBase({})
    base.seed(settled_day(NOW, ZONE), {"r1": 1.0})
    assert base.plan(NOW, ZONE) is None
    assert base.needs_reseed(NOW, ZONE) is False


def test_a_local_day_that_gains_an_hour_is_bounded_in_local_time() -> None:
    """Europe/Zurich leaves summer time on 25 October 2026: a 25-hour day."""
    base = EnergyBase({})
    base.seed(date(2026, 10, 24), {"r1": 0.0})
    plan = base.plan(datetime(2026, 10, 27, 9, tzinfo=timezone.utc), ZONE)
    assert (plan.first, plan.last) == (date(2026, 10, 25), date(2026, 10, 25))
    assert plan.end - plan.begin == 90000


def test_the_level_lives_in_the_managers_persisted_state() -> None:
    state: dict = {}
    base = EnergyBase(state)
    base.seed(date(2026, 11, 15), {"r1": 12.5})
    assert state["energy_base"] == {
        "settled_through": "2026-11-15",
        "levels": {"r1": 12.5},
    }
    assert EnergyBase(state).level("r1") == 12.5


def test_invalidating_forgets_the_level_so_the_next_cycle_seeds_again() -> None:
    """An import that rebuilds a series leaves a level describing values that
    no longer exist; forcing it back in lands the difference on one hour."""
    base = EnergyBase({})
    base.seed(settled_day(NOW, ZONE), {"r1": 646.083})
    assert base.needs_reseed(NOW, ZONE) is False

    base.invalidate()

    assert base.settled_through is None
    assert base.level("r1") is None
    assert base.hourly_start(ZONE) is None
    assert base.plan(NOW, ZONE) is None
    assert base.needs_reseed(NOW, ZONE) is True
