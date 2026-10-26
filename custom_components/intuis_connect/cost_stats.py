"""Energy cost contract: explicit prices applied to confirmed hourly kWh.

Adapted from TheFab21's cost proposal (#22/#24):
https://github.com/antoine-pyre/intuis-connect/pull/22
Unlike the proposal, a missing price is never replaced by the current or fixed
price, and costs are derived from confirmed kWh rather than re-fetched data.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
import math

from .hourly_series import HOUR

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
