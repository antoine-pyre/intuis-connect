# Hourly energy statistics

The hourly implementation adapts **TheFab21 #17/#22/#24**. Original sources are
linked in [CONTRIBUTORS.md](../CONTRIBUTORS.md); implementation progress is in
[the task journal](pr-integration-progress.md). Features below describe the
contract under development, not a published release.

## Identity and ownership

Daily sensors, their IDs, TOTAL_INCREASING, reset hour and freshness attributes
remain unchanged. External hourly series use source `intuis_connect` and IDs
`intuis_connect:energy_<digest>`. The digest is the first 32 SHA-256 hexadecimal
characters of compact JSON `[home_id,room_id]` (ASCII escaping enabled).
A home aggregate uses null as room_id; costs use the separate `cost_` prefix.
Entity renames, accented labels and shared room names cannot change identity.

The recorder metadata has sum=true, mean disabled, and kWh units. The new format
uses mean_type/unit_class on HA 2026.10 and has_mean on HA 2024.6. These series
are separate from recorder-owned daily sensor statistics. Energy dashboard device
consumption can select external sum/kWh series after their first confirmed write.
Choose the home aggregate OR its rooms when configuring totals, to avoid counting
the same consumption twice. The precise dashboard configuration is user-owned.
