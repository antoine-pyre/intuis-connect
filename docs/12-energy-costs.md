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

## Options

**Energy Costs** appears in the integration options after the energy step. It is
off by default and requires hourly statistics, since costs are computed from
confirmed hourly energy. Options are stored under `cost_*` keys, distinct from
the community `energy_cost_*` options of #22, which are neither read nor removed.

| Option | Values | Validation |
|---|---|---|
| Cost statistics | on/off | Off by default |
| Price source | Fixed price / Price entity | Required when enabled |
| Fixed price | -10 to 10 per kWh, any precision | Required for a fixed price; 0.25 is only a suggestion |
| Price entity | A `sensor` | Must exist and report `<currency>/kWh` |

The price history of an entity comes from the recorder. Hours older than the
recorder purge horizon (`purge_keep_days`, 10 days by default) have no recorded
price and are refused; keep enough history, or use a fixed price explicitly, for
older recalculations.

## Series and display

Each room and the home get an external cost series, separate from energy:
`intuis_connect:cost_<digest>` from the same `[home_id, room_id]` identity as the
energy series. Costs are written by the hourly import and updater, right after
the room's kWh are confirmed, from those exact kWh; each series is replaced in
one acknowledged recorder transaction. The home cost is the sum of room costs and
is only written when every room has a cost for the same hours.

A price problem never blocks or changes the energy import: the job reports
`costs` as `complete`, `partial` or `failed`, and the error names the cause.

A display sensor per room and for the home (`<name> Hourly Cost`, monetary, two
decimals) shows the last confirmed cumulative cost. It has no state class, so the
recorder does not compile a second cost series from it; select the external cost
series in the energy dashboard. Display sensors read the recorder at startup and
after each acknowledged write of their own home only.
