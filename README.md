# Intuis Connect – Home Assistant Integration

> **Full control of your Muller / Campa / Intuis electric radiators** with Netatmo "Intuitiv" modules – climate control, energy tracking, schedule management, and more.

[![HACS Badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/antoine-pyre/homeassistant-intuis-connect)](https://github.com/antoine-pyre/homeassistant-intuis-connect/releases)

---

## Features at a Glance

| Feature | Description |
|---------|-------------|
| **Climate Control** | Full thermostat control per room with Auto/Heat/Off modes |
| **Presets** | Schedule, Away, and Boost modes with configurable durations |
| **Energy Monitoring** | Daily kWh consumption per room with historical import |
| **Hourly Energy Statistics** | Accurate per-room kWh injected into HA Long-Term Statistics |
| **Energy Cost Tracking** | Automatic cost calculation per room, visible in the Energy Dashboard |
| **Schedule Management** | View, switch, and edit heating schedules |
| **Intuis Planning** | Standalone visual web interface for schedule editing *(new)* |
| **Calendar Integration** | Visualize weekly schedules as calendar events |
| **Smart Detection** | Presence detection, open window detection, heating anticipation |
| **Indefinite Override** | Keep manual temperatures active indefinitely |

---

## Installation

> **Requires Home Assistant 2024.6+ and HACS 1.33+**

### One-Click Install (Recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=antoine-pyre&repository=homeassistant-intuis-connect&category=integration)

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
| **Sensor** | `sensor.<room>_target_temperature` | Current setpoint (°C) |
| **Sensor** | `sensor.<room>_scheduled_temperature` | Temperature according to schedule |
| **Sensor** | `sensor.<room>_energy` | Hourly/daily energy consumption (kWh) — feeds the Energy Dashboard |
| **Sensor** | `sensor.<room>_cost` | Cumulative energy cost — feeds the Energy Dashboard |
| **Sensor** | `sensor.<room>_heating_minutes` | Heating time today |
| **Sensor** | `sensor.<room>_override_expires` | When manual override ends |
| **Binary Sensor** | `binary_sensor.<room>_presence` | Motion/presence detected |
| **Binary Sensor** | `binary_sensor.<room>_open_window` | Window open detected |
| **Binary Sensor** | `binary_sensor.<room>_anticipation` | Pre-heating active |
| **Binary Sensor** | `binary_sensor.<room>_boost` | Boost mode active |

### Per Schedule

| Entity Type | Name | Description |
|-------------|------|-------------|
| **Sensor** | `sensor.<schedule>_current_zone` | Currently active zone (Comfort, Night, Eco...) |
| **Sensor** | `sensor.<schedule>_next_zone_change` | When the next zone starts |
| **Sensor** | `sensor.<schedule>_summary` | Full schedule data (for cards) |
| **Calendar** | `calendar.<schedule>` | Weekly schedule visualization |

### Home Level

| Entity Type | Name | Description |
|-------------|------|-------------|
| **Select** | `select.intuis_active_schedule` | Switch between schedules |
| **Sensor** | Various config sensors | Home settings and configuration |

---

## Climate Modes & Presets

### HVAC Modes

| Mode | Description |
|------|-------------|
| **Auto** | Follow the active schedule |
| **Heat** | Manual temperature control |
| **Off** | Frost protection only |

### Presets

| Preset    | Description |
|-----------|-------------|
| **Home**  | Return to automatic schedule (mapped to HA Home preset) |
| **Away**  | Reduced temperature for extended absence |
| **Boost** | Maximum heating for quick warmup |
| **Eco**   | Minimum temperature for frost protection (mapped to HA Eco preset) |

All preset durations and temperatures are configurable in the integration options.

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

### `intuis_connect.sync_schedule`

Push a full timetable to the Intuis API (used internally by the planning interface).

```yaml
service: intuis_connect.sync_schedule
data:
  schedule_name: "Comfort"
  timetable: [...]
```

### `intuis_connect.set_zone_temperature`

Set the temperature of a zone for a specific room.

```yaml
service: intuis_connect.set_zone_temperature
data:
  room_name: "Living Room"
  zone_name: "Comfort"
  temperature: 20.5
```

### `intuis_connect.import_energy_history`

Import historical energy data from the Intuis cloud into HA Long-Term Statistics.

```yaml
service: intuis_connect.import_energy_history
data:
  days: 365
  granularity: "1hour"   # or "1day"
```

### `intuis_connect.recalculate_cost_history`

Recalculate energy cost statistics from existing kWh data, useful after changing the electricity price.

```yaml
service: intuis_connect.recalculate_cost_history
data:
  days: 365
```

---

## Energy Monitoring

### Hourly Statistics

The integration periodically fetches past hourly consumption data from the Intuis API and injects it directly into **Home Assistant Long-Term Statistics** via `async_import_statistics`. This makes per-room energy consumption available in the **Energy Dashboard** with accurate historical data.

- Statistics are updated at a configurable interval (default: every 2 hours)
- The Intuis API typically has a 2–4 hour delay before data is finalized
- Data is stored as cumulative kWh sums, compatible with the HA Energy Dashboard

### Energy Cost Tracking

When enabled, the integration calculates the cost of each room's energy consumption and writes it to a dedicated `sensor.<room>_cost` entity, also visible in the Energy Dashboard.

Two pricing modes are available:
- **Fixed price** — a constant €/kWh rate configured in the integration options
- **HA Entity** — reads the current price from any HA sensor (e.g. Octopus, Amber, or a template sensor)

To activate, go to **Settings → Devices & Services → Intuis Connect → Configure → Energy Cost**.

After changing the electricity price, use the `recalculate_cost_history` service to rewrite historical cost statistics.

### Historical Import

Use the `import_energy_history` service or enable it at setup time to backfill the Energy Dashboard with up to 730 days of historical data.

```yaml
service: intuis_connect.import_energy_history
data:
  days: 365
  granularity: "1hour"
```

---

## Intuis Planning — Visual Web Interface *(new)*

`intuis_planning.html` is a standalone single-file web application for visually editing your Intuis heating schedules.

### Usage Modes

**Embedded in Home Assistant** — place the file in `/config/www/` and add it to your dashboard:

```yaml
type: iframe
url: /local/intuis_planning.html
aspect_ratio: 100%
```

When loaded inside the HA iframe, the page accesses the `hass` object directly — no token required.

**Standalone browser access** — open the file in any browser. A configuration dialog prompts for:
- Your Home Assistant URL (e.g. `http://homeassistant.local:8123`)
- A long-lived access token (created under **Profile → Long-Lived Access Tokens**)
- An optional *Remember token* checkbox (stores credentials in `localStorage`; leave unchecked on shared computers)

In standalone mode, all communication goes through the HA REST API.

### Features

- **Full week grid** — each day is a horizontal bar with colored segments per zone; hour markers every 2 hours
- **Click to edit** — clicking any segment opens a dialog to change start time, end time (with next-day option), and zone
- **Add slots** — a `+` button on each day row adds a new time slot
- **Zone temperature editing** — zone cards below the grid allow per-room temperature adjustment with `+` / `−` buttons
- **Away & frost-guard temperatures** — editable directly from the top controls
- **Multi-schedule support** — dropdown lists all available schedules; the active one is marked with ✓
- **Change detection** — Save is only enabled when changes exist; switching schedule without saving prompts a confirmation
- **Save** — timetable changes pushed via `intuis_connect.sync_schedule`; temperature changes via `intuis_connect.set_zone_temperature` (one call per changed room); `refresh_schedules` triggered automatically after saving
- **Refresh** — 🔄 button triggers `refresh_schedules` and reloads state from HA
- **Light / Dark mode** — follows OS preference via `prefers-color-scheme`
- **Firefox / ES5 compatible** — no optional chaining, nullish coalescing, or template literals; works in HA's sandboxed iframe on Firefox
- **Post-restart resilience** — when embedded after a HA restart, waits up to 45 seconds for WebSocket reconnection with a live countdown; falls back to REST mode if unavailable

### Installation

Copy `intuis_planning.html` to your HA config folder:

```
/config/www/intuis_planning.html
```

Then add a panel in your dashboard:

```yaml
type: iframe
url: /local/intuis_planning.html
aspect_ratio: 100%
```

---

## Configuration Options

Accessible via **Settings → Devices & Services → Intuis Connect → Configure**

### Override Durations

| Option | Default | Range | Description |
|--------|---------|-------|-------------|
| Manual Duration | 5 min | 1-720 min | How long manual temperature lasts |
| Away Duration | 24 hours | 1-10080 min | How long away mode lasts |
| Boost Duration | 30 min | 1-720 min | How long boost mode lasts |

### Override Temperatures

| Option | Default | Range | Description |
|--------|---------|-------|-------------|
| Away Temperature | 16°C | 5-30°C | Temperature during away mode |
| Boost Temperature | 30°C | 5-30°C | Temperature during boost mode |

### Energy Settings

| Option | Default | Description |
|--------|---------|-------------|
| Energy Scale | 1 day | Granularity: 5min, 30min, 1hour, or 1day |
| Hourly Statistics | Off | Enable periodic injection of hourly kWh into LTS |
| Hourly Stats Interval | 2 hours | How often to fetch and inject hourly stats |
| Import History | Off | Import historical energy data on setup |
| History Days | 30 | Days of history to import (7, 30, 90, 365) |

### Energy Cost

| Option | Default | Description |
|--------|---------|-------------|
| Enable Cost Calculation | Off | Calculate and track energy cost per room |
| Pricing Mode | Fixed | `fixed` (€/kWh) or `entity` (HA sensor) |
| Fixed Price | 0.25 €/kWh | Rate used in fixed pricing mode |
| Price Entity | — | HA sensor providing current price in €/kWh |

### Special Modes

| Option | Default | Description |
|--------|---------|-------------|
| Indefinite Mode | Off | Auto-reapply overrides before they expire |

---

## Schedule Management

### Viewing Schedules

- **Calendar entities** show weekly schedules as events
- **Schedule summary sensor** contains full timetable data
- **Current zone sensor** shows what zone is active now
- **Next zone change sensor** shows upcoming transitions

### Editing Schedules

Use the **Intuis Planning** web interface (see above), the `set_schedule_slot` service, or install the [Intuis Schedule Card](https://github.com/antoine-pyre/intuis-schedule-card) for visual editing.

### Schedule Structure

Schedules contain **zones** (Comfort, Night, Eco, etc.) with:
- Temperature settings per room
- Weekly timetable (minute-precision, 0–10080 minutes from Monday 00:00)

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

### Visual Schedule Editor (Planning Interface)

```yaml
type: iframe
url: /local/intuis_planning.html
aspect_ratio: 100%
```

### Visual Schedule Editor (Card)

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
- Energy is only fetched after 2 AM for daily scale
- Check that rooms have associated bridge IDs
- Try switching to a different energy scale

### Energy Dashboard shows no data or negative values
- Enable **Hourly Statistics** in the integration options
- Use `import_energy_history` to backfill historical data
- If cost values look wrong after a price change, run `recalculate_cost_history`

### Schedule changes not appearing
- Click the refresh button or call `refresh_schedules`
- Changes made in the Intuis app may take 2 minutes to sync

### Intuis Planning not loading
- Ensure `intuis_planning.html` is in `/config/www/`
- In standalone mode, verify your HA URL and long-lived access token
- After a HA restart, the page waits up to 45 seconds before falling back to REST mode

### Authentication errors
- Re-authenticate by removing and re-adding the integration
- Check if your password changed in the Intuis app

---

## Technical Details

- **Update interval**: 2 minutes (configurable)
- **API**: Uses Netatmo cloud endpoints
- **Multi-cluster**: Automatic failover between API endpoints
- **Token refresh**: Automatic with 60-second buffer
- **Statistics backend**: `async_import_statistics` with `source="recorder"` (idempotent UPSERT — no conflicts with HA's internal recorder)

---

## Related Projects

- **[Intuis Schedule Card](https://github.com/antoine-pyre/intuis-schedule-card)** - Visual schedule editor card for Lovelace

---

## License

MIT License - see [LICENSE](LICENSE) for details.

## Credits

Created by [antoine-pyre](https://github.com/antoine-pyre)

Based on reverse-engineering of the Intuis/Netatmo API.
