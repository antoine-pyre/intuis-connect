# Energy cost statistics

The cost implementation adapts **TheFab21 #22/#24**. Sources are linked in
[CONTRIBUTORS.md](../CONTRIBUTORS.md); progress is in
[the task journal](pr-integration-progress.md). This page describes the contract
under development, not a published release.

## Currency, unit and precision

Costs use the currency configured in Home Assistant (**Settings → System →
General**), the same one as the energy dashboard. A cost series stores that
currency as its unit when it is created. If the HA currency later changes, the
existing series is not converted: recalculation is refused until the change is
handled explicitly.

Prices are expressed per kWh. A price entity must report `<currency>/kWh`, for
example `EUR/kWh`; for the euro, pound and dollar the symbol form
(`€/kWh`) is also accepted. Wh, MWh or another currency are refused rather than
converted. Statistics keep full floating-point precision: rounding each hour
would accumulate drift in the running sum. Display entities round to two
decimals.

## Price conventions

- **Fixed price**: the configured value applies only to the period explicitly
  requested by a recalculation or written by a later update. It never rewrites
  hours outside that period. No price is applied before it is configured, even
  if a default value is suggested in the form.
- **Price entity**: each hour uses the entity state in force at the start of the
  hour, read from the recorder history. The current state is never applied
  retroactively.
- Negative prices are valid (some dynamic tariffs pay for consumption).
  Negative energy remains invalid and is refused by the hourly import.

## Intra-hour approximation

Energy is only known per hour. When the price changes inside an hour, the whole
hour is charged at the price in force at its start. Over a day the error is
bounded by the consumption of the hours containing a price change multiplied by
the price difference; tariffs that change on the hour are exact.

## Gaps

A cost hour requires a confirmed hourly kWh value and a valid price. If the
price entity has no history, or is `unavailable`, `unknown` or non-numeric at the
start of an hour of the requested period, the period is refused with an error
naming that hour and its previous cost statistics are kept. A gap is never filled
with zero, the current price or the fixed price.
