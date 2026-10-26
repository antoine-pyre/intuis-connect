# Intuis Connect – Home Assistant Integration

> **Full control of your Muller / Campa / Intuis electric radiators** with Netatmo "Intuitiv" modules – climate control, energy tracking, schedule management, and more.

[![HACS Badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/antoine-pyre/intuis-connect)](https://github.com/antoine-pyre/intuis-connect/releases)

---

## Features at a Glance

| Feature | Description |
|---------|-------------|
| **Climate Control** | Full thermostat control per room with Auto/Heat/Off modes |
| **Presets** | Schedule, Away, and Boost modes with configurable durations |
| **Energy Monitoring** | Daily kWh consumption per room with historical import |
| **Schedule Management** | View, switch, and edit heating schedules |
| **Calendar Integration** | Visualize weekly schedules as calendar events |
| **Smart Detection** | Presence detection, open window detection, heating anticipation |
| **Indefinite Override** | Keep manual temperatures active indefinitely |

---

## Installation

> **Requires Home Assistant 2024.6+ and HACS 1.33+**

### One-Click Install (Recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=antoine-pyre&repository=intuis-connect&category=integration)

### Manual HACS Install

1. Open **HACS → Integrations**
2. Click **⋮** → **Custom repositories**
3. Add:
   - URL: `https://github.com/antoine-pyre/intuis-connect`
   - Category: **Integration**
4. Search for "Intuis Connect" → **Download** → **Restart** Home Assistant

### Configuration

1. Go to **Settings → Devices & Services → + Add Integration**
2. Search for **Intuis Connect**
3. Enter your Intuis/Muller app credentials (email & password)
4. Configure options (durations, temperatures, energy settings)

---

## Entities Created

### Per Room

| Entity Type | Name | Description |
|-------------|------|-------------|
| **Climate** | `climate.<room>` | Full thermostat control |
| **Sensor** | `sensor.<room>_temperature` | Current room temperature (°C) |
| **Sensor** | `sensor.<room>_scheduled_temperature` | Temperature according to schedule |
| **Sensor** | `sensor.<room>_energy` | Daily energy consumption (kWh) |
| **Sensor** | `sensor.<room>_heating_minutes` | Heating time today |
| **Sensor** | `sensor.<room>_override_expires` | When manual override ends |
| **Binary Sensor** | `binary_sensor.<room>_presence` | Motion/presence detected |
| **Binary Sensor** | `binary_sensor.<room>_open_window` | Window open detected |
| **Binary Sensor** | `binary_sensor.<room>_anticipation` | Pre-heating active |

### Per Schedule

| Entity Type | Name | Description |
|-------------|------|-------------|
| **Sensor** | `sensor.<schedule>_summary` | Full schedule data (for cards) |
| **Calendar** | `calendar.<schedule>` | Weekly schedule visualization |

### Home Level

| Entity Type | Name | Description |
|-------------|------|-------------|
| **Select** | `select.intuis_active_schedule` | Switch between schedules |
| **Sensor** | Current zone / next zone change | Active schedule transitions for this home |
| **Sensor** | Various config sensors | Home settings and configuration |

---

## Climate Modes & Presets

### HVAC Modes

| Mode | Description |
|------|-------------|
| **Auto** | Follow the active schedule |
| **Heat** | Manual temperature control |
| **Off** | Send the cloud off mode |

### Presets

| Preset    | Description |
|-----------|-------------|
| **Home**  | Return to automatic schedule (mapped to HA Home preset) |
| **Away**  | Reduced temperature for extended absence |
| **Boost** | Temporary boost using the configured setpoint |
| **Eco**   | Minimum temperature for frost protection (mapped to HA Eco preset) |

Manual, Away and Boost durations and the Away/Boost temperatures are configurable in the integration options. Frost protection uses the current defaults of 7°C and 365 days. Climate commands are shown as assumed state for at most 120 seconds while awaiting confirmation; subsequent cloud updates determine the displayed mode. See [heating state and persistence](docs/09-heating-overrides.md).

---

## Services

### `intuis_connect.switch_schedule`

Switch to a different heating schedule.

```yaml
service: intuis_connect.switch_schedule
data:
  schedule_name: "Comfort"
```

### `intuis_connect.set_schedule_slot`

Edit a time slot in the active schedule. Supports multi-day spans.

```yaml
service: intuis_connect.set_schedule_slot
data:
  start_day: "4"        # Friday (0=Monday, 6=Sunday)
  start_time: "22:00"
  end_day: "5"          # Saturday
  end_time: "08:00"
  zone_name: "Night"
```

### `intuis_connect.refresh_schedules`

Force refresh all schedule data from the Intuis API.

```yaml
service: intuis_connect.refresh_schedules
```

---

## Multi-Home Services

All domain services accept optional `home_id` to target an Intuis home. Without
it, planning mutations use the first loaded home (with a warning if several are
loaded), while refresh and history import target all homes. A nonempty import
`room_name` filters homes containing that room. Unknown or blank explicit home
IDs are rejected before any command.

Schedule, zone and room names are text inputs validated against the target home’s
current data. Run `refresh_schedules` after renaming them; no restart is needed.
Installed `services.yaml` is static and is never rewritten with account data.
See [multi-home service examples and lifecycle](docs/10-multi-home-services.md).

## Configuration Options

Accessible via **Settings → Devices & Services → Intuis Connect → Configure**

### Override Durations

| Option | Default | Range | Description |
|--------|---------|-------|-------------|
| Manual Duration | 60 min | Choices from 15-720 min | How long manual temperature lasts |
| Away Duration | 4 hours | Choices from 60-10080 min | How long away mode lasts |
| Boost Duration | 30 min | Choices from 15-720 min | How long boost mode lasts |

### Override Temperatures

| Option | Default | Range | Description |
|--------|---------|-------|-------------|
| Away Temperature | 16°C | 5-30°C | Temperature during away mode |
| Boost Temperature | 22°C | 5-30°C | Temperature during boost mode |

### Energy Settings

| Option | Default | Description |
|--------|---------|-------------|
| Energy Scale | 1 day | Granularity: 5min, 30min, 1hour, or 1day |
| Import History | Off | Import historical energy data on setup |
| History Days | 365 | Setup choices: 30, 90, 180, 365, 730 days |
| Energy Reset Hour | 02:00 | Configured boundary for daily counters |
| Hourly Statistics | Off | Opt-in separate hourly statistics per room and home |
| Hourly Update Interval | 2 hours | 1, 2, 4 or 6 hours between hourly updates |
| Energy Costs | Off | Opt-in hourly costs from a fixed price or a price sensor (requires hourly statistics) |

### Special Modes

| Option | Default | Description |
|--------|---------|-------------|
| Indefinite Mode | Off | Auto-reapply overrides before they expire |

---

## Energy Monitoring

The integration tracks energy consumption per room:

- **Daily consumption** in kWh
- **Heating minutes** per day
- **Historical import** available (up to 730 complete local days)
- Historical imports replace complete local days only and preserve existing statistics on failure.
  Let energy sensors record their first live statistics before importing; if the automatic
  setup attempt reports a missing live baseline, wait and retry the import service.
  See [safe import prerequisites and recovery](docs/08-safe-energy-history-import.md).
- **Hourly statistics** (opt-in): closed hours in separate external statistics per room and
  for the home, kept up to date automatically; `import_energy_history` with
  `granularity: hourly` fills older periods. The `1hour` energy scale is unrelated: it only
  refreshes the daily sensors. See [hourly energy statistics](docs/11-hourly-energy.md).
- **Energy costs** (opt-in): hourly cost statistics per room and for the home from confirmed
  hourly energy and an explicit price (fixed or a `<currency>/kWh` sensor); missing prices are
  refused, never guessed. `recalculate_cost_history` rewrites past costs. See
  [energy costs](docs/12-energy-costs.md).
- **Multiple tariff support** (aggregates all EJP tariffs)

Energy data is fetched based on your configured scale:
- `1day`: Successful measurements cached per room after the configured reset hour (02:00 by default); failed rooms retry on the next cycle
- `5min/30min/1hour`: Measurements refreshed each polling cycle
- Missing readings are not fabricated as zero. The last valid measurement retains its date and freshness attributes; an incomplete home aggregate is marked stale.

---

## Schedule Management

### Viewing Schedules

- **Calendar entities** show weekly schedules as events
- **Schedule summary sensor** contains full timetable data
- **Current zone sensor** shows what zone is active now
- **Next zone change sensor** shows upcoming transitions

### Editing Schedules

Use the `set_schedule_slot` service or install the [Intuis Schedule Card](https://github.com/antoine-pyre/intuis-schedule-card) for visual editing.

### Schedule Structure

Schedules contain **zones** (Comfort, Night, Eco, etc.) with:
- Temperature settings per room
- Weekly timetable (minute-precision, 0-10080 minutes from Monday 00:00)

---

## Dashboard Examples

### Thermostat Card

```yaml
type: thermostat
entity: climate.living_room
```

### Boost Button

```yaml
type: button
icon: mdi:fire
name: Boost 30 min
tap_action:
  action: call-service
  service: climate.set_preset_mode
  target:
    entity_id: climate.living_room
  data:
    preset_mode: boost
```

### Away Button

```yaml
type: button
icon: mdi:home-export-outline
name: Away Mode
tap_action:
  action: call-service
  service: climate.set_preset_mode
  target:
    entity_id: climate.living_room
  data:
    preset_mode: away
```

### Schedule Selector

```yaml
type: entities
entities:
  - entity: select.intuis_active_schedule
```

### Energy History Graph

```yaml
type: history-graph
entities:
  - entity: sensor.living_room_energy
hours_to_show: 168
```

### Visual Schedule Editor

Install the companion [Intuis Schedule Card](https://github.com/antoine-pyre/intuis-schedule-card):

```yaml
type: custom:intuis-schedule-card
entity: sensor.intuis_home_schedule_summary
```

---

## Smart Features

### Presence Detection
Detects motion in rooms (sensor updates every 2 minutes).

### Open Window Detection
Automatically detects open windows to pause heating.

### Heating Anticipation
Pre-heats rooms before scheduled zone changes.

### Indefinite Override Mode
When enabled, the integration automatically re-applies manual overrides before they expire, effectively making them permanent until you switch back to schedule mode.

---

## Troubleshooting

### Climate entity not responding
- Check Home Assistant logs for API errors
- Verify your Intuis credentials are still valid
- Try the `refresh_schedules` service

### Energy data missing
- Daily-scale energy is fetched after the configured reset hour (02:00 by default)
- Check that rooms have associated bridge IDs
- Try switching to a different energy scale

### Schedule changes not appearing
- Click the refresh button or call `refresh_schedules`
- Call `refresh_schedules` after editing schedule definitions in the Intuis app; room status is polled normally

### Authentication errors
- Re-authenticate by removing and re-adding the integration
- Check if your password changed in the Intuis app

---

## Technical Details

- **Update interval**: 2 minutes (configurable)
- **API**: Uses Netatmo cloud endpoints
- **Multi-cluster**: Automatic failover between API endpoints
- **Token refresh**: Automatic with 60-second buffer

---

## Related Projects

- **[Intuis Schedule Card](https://github.com/antoine-pyre/intuis-schedule-card)** - Visual schedule editor card for Lovelace

---

## License

MIT License - see [LICENSE](LICENSE) for details.

## Credits

Created by [antoine-pyre](https://github.com/antoine-pyre)

See [Contributors and contribution sources](CONTRIBUTORS.md) for contributor
credits, original pull requests, and attribution of planned adaptations.

Based on reverse-engineering of the Intuis/Netatmo API.

## Development

See [Development and validation](docs/development.md) for the pinned Python/Home
Assistant test matrix, offline test fixtures, and the same checks used in CI.
