"""Energy cost contract: explicit prices applied to confirmed hourly kWh.

Adapted from TheFab21's cost proposal (#22/#24):
https://github.com/antoine-pyre/intuis-connect/pull/22
Unlike the proposal, a missing price is never replaced by the current or fixed
price, and costs are derived from confirmed kWh rather than re-fetched data.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
import math
from typing import Any

from homeassistant.components.recorder import get_instance, history, statistics
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .external_statistics import metadata, statistic_id
from .hourly_series import HOUR
from .recorder_import import ExternalReplacementResult, async_replace_external_history
from .utils.const import (
    DOMAIN,
    CONF_COST_FIXED_PRICE,
    CONF_COST_PRICE_ENTITY,
    CONF_COST_PRICE_MODE,
    CONF_COST_STATISTICS,
    CONF_HOURLY_STATISTICS,
)

PRICE_MODE_FIXED = "fixed"
PRICE_MODE_ENTITY = "entity"
# Some price integrations publish the euro symbol instead of the ISO code.
CURRENCY_SYMBOLS = {"EUR": "€", "USD": "$", "GBP": "£"}


class CostPriceError(Exception):
    """A price is missing or invalid; the affected period is refused."""


def parse_price(value: object) -> float | None:
    """Return a finite price, negative prices included, or None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            return None
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def price_unit_matches(unit: str | None, currency: str) -> bool:
    """Accept only <currency>/kWh; no implicit Wh/MWh or currency conversion."""
    if not isinstance(unit, str):
        return False
    accepted = {f"{currency}/kWh"}
    if symbol := CURRENCY_SYMBOLS.get(currency):
        accepted.add(f"{symbol}/kWh")
    return unit.replace(" ", "") in accepted


def prices_at_hours(
    changes: Sequence[tuple[float, object]], hours: Sequence[int]
) -> tuple[float, ...]:
    """Price in force at the start of each hour, from sorted state changes.

    The state known at the hour start applies to the whole hour. A missing,
    unavailable or non-numeric state refuses the period instead of guessing.
    """
    result = []
    index = -1
    for hour in hours:
        while index + 1 < len(changes) and changes[index + 1][0] <= hour:
            index += 1
        price = parse_price(changes[index][1]) if index >= 0 else None
        if price is None:
            raise CostPriceError(
                f"No valid price at {datetime.fromtimestamp(hour, timezone.utc).isoformat()}; "
                "cost statistics for this period were preserved"
            )
        result.append(price)
    return tuple(result)


def fixed_prices(price: object, hours: Sequence[int]) -> tuple[float, ...]:
    """A configured fixed price applies only to the period explicitly requested."""
    value = parse_price(price)
    if value is None:
        raise CostPriceError("The configured fixed price is not a finite number")
    return (value,) * len(hours)


def hourly_costs(
    energy: Sequence[tuple[datetime, float]], prices: Sequence[float]
) -> tuple[tuple[datetime, float], ...]:
    """Unrounded hourly cost; rounding is a display concern only."""
    if len(energy) != len(prices):
        raise CostPriceError("Each confirmed hour needs exactly one price")
    previous = None
    for start, kwh in energy:
        ts = start.timestamp()
        if ts % HOUR or (previous is not None and ts != previous + HOUR):
            raise CostPriceError("Cost hours must be contiguous closed hours")
        if (
            isinstance(kwh, bool)
            or not isinstance(kwh, (int, float))
            or not (math.isfinite(kwh) and kwh >= 0)
        ):
            raise CostPriceError("Confirmed energy must be finite and nonnegative")
        previous = ts
    return tuple((start, kwh * price) for (start, kwh), price in zip(energy, prices))


def validate_cost_options(
    options: dict[str, Any], currency: str, hass: HomeAssistant | None = None
) -> dict[str, str]:
    """Return form errors; an enabled cost feature needs an explicit price source."""
    if not options.get(CONF_COST_STATISTICS):
        return {}
    errors = {}
    if not options.get(CONF_HOURLY_STATISTICS):
        errors[CONF_COST_STATISTICS] = "cost_requires_hourly"
    mode = options.get(CONF_COST_PRICE_MODE)
    if mode == PRICE_MODE_FIXED:
        if parse_price(options.get(CONF_COST_FIXED_PRICE)) is None:
            errors[CONF_COST_FIXED_PRICE] = "fixed_price_required"
    elif mode == PRICE_MODE_ENTITY:
        entity_id = options.get(CONF_COST_PRICE_ENTITY)
        state = hass.states.get(entity_id) if hass and entity_id else None
        if state is None:
            errors[CONF_COST_PRICE_ENTITY] = "price_entity_not_found"
        elif not price_unit_matches(
            state.attributes.get("unit_of_measurement"), currency
        ):
            errors[CONF_COST_PRICE_ENTITY] = "price_entity_unit"
    else:
        errors[CONF_COST_PRICE_MODE] = "price_mode_required"
    return errors


async def async_price_changes(
    hass: HomeAssistant, entity_id: str, start: datetime, end: datetime, currency: str
) -> list[tuple[float, object]]:
    """Recorded price states, including the one in force at `start`.

    A state whose unit is not <currency>/kWh counts as missing, not converted.
    History older than the recorder's purge horizon is a gap.
    """

    # HA returns changes strictly after start_time and the start state strictly
    # before it, so a change exactly on the hour would be lost: query 1 ms earlier.
    since = start - timedelta(milliseconds=1)

    def read():
        return history.state_changes_during_period(
            hass, since, end, entity_id, False, False, None, True
        )

    states = (await get_instance(hass).async_add_executor_job(read)).get(entity_id, [])
    return [
        (
            state.last_changed.timestamp(),
            state.state
            if price_unit_matches(state.attributes.get("unit_of_measurement"), currency)
            else None,
        )
        for state in states
    ]


async def async_hour_prices(
    hass: HomeAssistant, options: dict[str, Any], currency: str, hours: Sequence[int]
) -> tuple[float, ...]:
    """Prices for contiguous closed hours, from the configured explicit source."""
    if not hours:
        return ()
    mode = options.get(CONF_COST_PRICE_MODE)
    if mode == PRICE_MODE_FIXED:
        return fixed_prices(options.get(CONF_COST_FIXED_PRICE), hours)
    if mode != PRICE_MODE_ENTITY or not options.get(CONF_COST_PRICE_ENTITY):
        raise CostPriceError("No price source is configured")
    changes = await async_price_changes(
        hass,
        options[CONF_COST_PRICE_ENTITY],
        datetime.fromtimestamp(hours[0], timezone.utc),
        datetime.fromtimestamp(hours[-1] + HOUR, timezone.utc),
        currency,
    )
    return prices_at_hours(changes, hours)


def cost_signal(entry_id: str) -> str:
    """Per-entry signal: one home's cost writes never refresh another's sensors."""
    return f"{DOMAIN}_cost_updated_{entry_id}"


def cost_metadata(
    home_id: str, room_id: str | None, label: str, currency: str
) -> dict[str, Any]:
    return metadata(
        home_id, room_id, f"{label} hourly cost", kind="cost", currency=currency
    )


async def async_write_costs(
    hass: HomeAssistant,
    meta_data: dict[str, Any],
    costs: tuple[tuple[datetime, float], ...],
) -> ExternalReplacementResult:
    """Replace one cost series in a single acknowledged transaction."""
    return await async_replace_external_history(
        hass,
        meta_data,
        costs[0][0],
        datetime.fromtimestamp(costs[-1][0].timestamp() + HOUR, timezone.utc),
        costs,
    )


def async_publish_costs(hass: HomeAssistant, entry_id: str) -> None:
    """Notify display sensors; called only after an acknowledged write."""
    async_dispatcher_send(hass, cost_signal(entry_id))


async def async_last_cost(
    hass: HomeAssistant, home_id: str, room_id: str | None
) -> tuple[float, datetime] | None:
    """Last confirmed cumulative cost and the hour it ends, from the recorder."""
    sid = statistic_id(home_id, room_id, "cost")
    rows = await get_instance(hass).async_add_executor_job(
        statistics.get_last_statistics, hass, 1, sid, False, {"sum"}
    )
    if not rows.get(sid) or rows[sid][0].get("sum") is None:
        return None
    start = rows[sid][0]["start"]
    start_ts = start.timestamp() if isinstance(start, datetime) else start
    return rows[sid][0]["sum"], datetime.fromtimestamp(start_ts + HOUR, timezone.utc)
