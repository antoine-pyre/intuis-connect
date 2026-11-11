# Pilot-wire rooms (FP4)

Local implementation, not yet released. Adapted from
[apeyrat's proposal #27](https://github.com/antoine-pyre/intuis-connect/issues/27),
[the original implementation](https://github.com/adrienvsj/intuis-connect/commit/6eb642b73539cee2c642b80e7bbb2dbbcd35695d)
and [adrienvsj's detection correction](https://github.com/adrienvsj/intuis-connect/commit/04b79ef755ae794240c6fa1507a1a5fce1e5b139).
Data-parsing protections also adapt ideas from
[adrienvsj's partial-data fixes](https://github.com/adrienvsj/intuis-connect/commit/598e6359298493a9dd0c1da03dfb14619603d748).

## Behaviour

A room is treated as pilot-wire when its reported type starts with `FP`, both
measured and target temperatures are absent, and a recognised
`therm_setpoint_fp` order is reported. FP rooms that report either temperature
keep the existing thermostat entity. Missing temperatures alone do not select
the pilot-wire class. This remains a capability heuristic, not a cloud capability
flag; physical FP variants still require validation.

The climate entity keeps its existing unique ID. It exposes Comfort, Eco and
Frost protection presets and no temperature dial. Commands use manual mode with
`therm_setpoint_fp` (`comfort`, `away`, `frost_guard`), an end time and no numeric
temperature. Heat selects manual Comfort, Auto resumes the home schedule and Off
sends the existing off command. Manual pilot-wire orders use the configured
manual duration. Temperature setpoints and the thermostat Boost preset are
rejected for these rooms. An order alone does not claim actual heating activity.

Orders use the shared command lock and the existing bounded pending state. An
acknowledgement must match the wire order and observed expiry. Accepted orders
are persisted in the existing overrides storage with an optional `fp` key and
can be reapplied in indefinite mode. Existing temperature-only records remain
readable. Returning to Auto/Off clears the saved manual intention.

## Partial responses and compatibility

Unknown or malformed status-room entries are skipped without preventing updates
for known rooms. Missing/null temperatures remain unknown rather than becoming
0 °C. Temperature-based heating estimation requires both values and is disabled
for Off mode. Missing rooms make their climate entities unavailable; a partial
status does not delete intentions for rooms still present in home definitions.

Climate native temperature properties are exposed for newer Home Assistant
cores. Legacy property aliases and attributes are defined only when the installed
core still uses the legacy climate API, preserving the HA 2024.6 minimum.

## Validation limits

`tests/unit/test_pilot_wire.py` covers selection, parsing, commands, transport,
refusals, acknowledgements, persistence/reload and reapplication with the native
HA Store. `test_heating_reconciliation.py` also checks an empty status followed
by recovery. Transport responses are simulated; no cloud account or physical
radiator is controlled. Actual order acceptance and behaviour on FP4 hardware
remain to be confirmed by users.

## Included in the updated 2.1.0 beta

The FP4 work was initially prepared separately on `codex/2.2.0-beta`. At the
maintainer's request, that branch is merged into the updated 2.1.0 beta. There
is no separate 2.2.0 release. Existing installations of the earlier 2.1.0 beta
need to redownload that beta and restart Home Assistant to obtain these changes.

The combined branch passes **570 tests on HA 2024.6.4 / Python 3.12 and 570 on
HA 2026.10.4 / Python 3.14**, including temperature API compatibility tests.
Ruff passes on both environments. The cloud transport is simulated and physical
FP4 acceptance remains to be confirmed; no comment is sent to the reporter.
