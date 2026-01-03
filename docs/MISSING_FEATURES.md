# Intuis Connect: Missing Features Analysis

This document lists features available in the Intuis API that are not yet implemented in the Home Assistant integration, along with implementation recommendations.

---

## Currently Implemented

### API Endpoints
- `POST /oauth2/token` - Authentication and token refresh
- `GET /api/homesdata` - Homes, rooms, modules, schedules
- `POST /syncapi/v1/homestatus` - Live home status
- `POST /syncapi/v1/getconfigs` - Configuration and schedules
- `POST /syncapi/v1/setstate` - Room mode and temperature control
- `POST /api/gethomemeasure` - Home energy consumption
- `POST /api/getroommeasure` - Room energy consumption
- `POST /api/synchomeschedule` - Create/update schedules
- `POST /api/switchhomeschedule` - Switch active schedule
- `GET /api/gethomeschedule` - Get schedule details

### Platforms
- Climate, Sensor, Binary Sensor, Select, Number, Calendar

### Services
- `switch_schedule`, `set_schedule_slot`, `refresh_schedules`, `set_zone_temperature`, `import_energy_history`

### Recently Implemented

#### Rate Limit Handling (v1.9.1)
- Circuit breaker pattern (pauses requests after consecutive 429s)
- Request throttling (minimum delay between API calls)
- Adaptive polling (increases interval when rate limited, recovers when stable)
- Retry-After header support
- User-configurable settings in integration options

#### Module/Gateway Health Sensors (v1.9.0)
- `binary_sensor.{room}_{module}_reachable` - Module connectivity status
- `sensor.{room}_{module}_last_seen` - Last communication timestamp
- `sensor.{room}_{module}_firmware` - Module firmware version (diagnostic)
- `sensor.gateway_wifi_strength` - Gateway WiFi signal strength
- `sensor.gateway_uptime` - Gateway uptime with formatted attribute
- `sensor.gateway_firmware` - Gateway firmware version (diagnostic)

#### Configurable Energy Reset Time (v1.9.0)
- Energy sensors reset at configurable hour (default 2 AM)
- "Logical day" concept for accurate daily tracking
- Configurable in integration options

#### Historical Energy Import (v1.9.0)
- Import historical energy data from Intuis cloud
- Available as setup option or service call
- Imports to existing sensor entities for Energy Dashboard

#### Home-Level Energy Aggregation (v1.9.0)
- `sensor.intuis_home_energy_today` - Total home energy consumption
- Aggregates energy from all room sensors
- Includes `room_breakdown` attribute with per-room values
- Uses same daily reset logic as room sensors

---

## Planned Features

### 1. Delete Schedule Slot

**Interest:**
Users can create schedule slots but cannot delete individual slots without rewriting the entire schedule. This forces workarounds like setting a slot to minimal duration or using the mobile app.

**Requirements:**
- API endpoint: `DELETE https://connect.intuis.net/api/deletenewhomeschedule`
- Parameters: `schedule_id`, `slot_id` or time range identifier
- Authentication: Standard OAuth2 token

**HA Integration:**
- New service: `intuis_connect.delete_schedule_slot`
- Schema: `schedule_name`, `day`, `start_time`
- Updates `services.yaml` dynamically like existing services

---

### 2. Tariff-Separated Energy Sensors

**Interest:**
The API provides energy data split by tariff (`sum_energy_elec$0`, `$1`, `$2`) for off-peak, peak, and super-peak periods. This enables accurate cost calculations and optimization of consumption during cheaper periods.

**Requirements:**
- API endpoint: `POST /api/getroommeasure` (already used)
- Change: Request each tariff type separately
- Data fields: `sum_energy_elec$0`, `sum_energy_elec$1`, `sum_energy_elec$2`

**HA Integration:**
- New sensors per room: `sensor.{room}_energy_tariff_0`, `_tariff_1`, `_tariff_2`
- Optional: Make tariff sensors configurable (enable/disable in config flow)
- Add utility meter integration compatibility for cost tracking
- Include tariff metadata as attributes (if available from API)

**Why this can't be a template:** The API tracks which kWh were consumed during each tariff period. This data isn't derivable from the total energy sensor.

---

### 3. Away/Frost Temperature Configuration

**Interest:**
Each schedule has `away_temp` and `hg_temp` (frost protection) settings. Users cannot modify these without the mobile app. Useful for seasonal adjustments or vacation settings.

**Requirements:**
- API endpoint: `POST /api/synchomeschedule` (already used)
- Fields: `away_temp`, `hg_temp` in schedule payload
- Must preserve existing schedule data when updating

**HA Integration:**
- New service: `intuis_connect.set_schedule_temperatures`
- Schema: `schedule_name`, `away_temp` (optional), `frost_temp` (optional)
- Alternative: Number entities for each schedule's away/frost temps
- Validate temperature ranges (typically 5-19°C for frost, 10-25°C for away)

---

### 4. Schedule Conflict Detection

**Interest:**
Creating overlapping schedule slots causes unpredictable behavior. Validation before API calls prevents user errors and improves reliability.

**Requirements:**
- No API change needed
- Client-side validation in `set_schedule_slot` service
- Compare new slot against existing timetable entries

**HA Integration:**
- Add validation in `async_handle_set_schedule_slot()`
- Raise `HomeAssistantError` with clear message on conflict
- Log warning with conflicting slot details
- Optional: Auto-adjust adjacent slots to prevent overlap

---

### 5. Anticipation Control

**Status:** Needs API investigation

**Interest:**
The system pre-heats rooms to reach target temperature on time ("anticipation"). Users may want to disable this during mild weather or enable it during cold snaps manually.

**Requirements:**
- Investigation needed: Check if API supports anticipation toggle
- Current: `anticipation` binary sensor exists (read-only)
- May require `/syncapi/v1/setstate` with specific parameters

**HA Integration:**
- New switch: `switch.{room}_anticipation` (if API supports)
- Alternative: Service to temporarily disable anticipation
- If read-only, document limitation and keep binary sensor only

---

## Won't Implement

The following features were considered but won't be implemented because they're better served by Home Assistant's native capabilities or provide marginal value given the async/cloud-polling nature of the integration.

### Boost Status Binary Sensor
**Reason:** Redundant with `climate.preset_mode` attribute.

Users can create a template if needed:
```yaml
template:
  - binary_sensor:
      - name: "Room Boost Active"
        state: "{{ state_attr('climate.room', 'preset_mode') == 'boost' }}"
```

### Home Presence Aggregation Sensor
**Reason:** Trivially done with HA's group platform.

```yaml
binary_sensor:
  - platform: group
    name: "Home Presence"
    device_class: occupancy
    entities:
      - binary_sensor.room1_presence
      - binary_sensor.room2_presence
```

### Batch Room Control Service
**Reason:** Marginal benefit with rate limiting in place. Multiple service calls work fine. Atomicity isn't guaranteed anyway due to async polling (2-minute interval).

### Schedule Duplication Service
**Reason:** Rare operation (once per season). Mobile app handles this adequately. Low value vs implementation complexity.

### Historical Energy Export Service
**Reason:** Now redundant. The `import_energy_history` service populates HA statistics database. Users can export data from Home Assistant's Energy Dashboard.

### Heating Efficiency Metrics
**Reason:** Wrong abstraction layer. Requires external data (outdoor temperature) and complex calculations. Better implemented as:
- User-created template sensors
- Separate analytics integration
- HA's statistics features

### Rate Limit Status Sensor
**Reason:** Mostly addressed by circuit breaker implementation. The Intuis API doesn't return rate limit headers (`X-RateLimit-Remaining`, etc.). Users don't need real-time quota visibility - the circuit breaker handles recovery automatically.

### Multi-Home Energy Aggregation
**Reason:** Niche use case + trivially templated.

```yaml
template:
  - sensor:
      - name: "All Homes Energy"
        unit_of_measurement: "kWh"
        state: >
          {{ states('sensor.home1_energy_today') | float(0) +
             states('sensor.home2_energy_today') | float(0) }}
```

---

## Implementation Priority Matrix

| Priority | Feature | Effort | Impact |
|----------|---------|--------|--------|
| P1 | Schedule conflict detection (#4) | Low | Medium |
| P2 | Tariff-separated energy (#2) | Medium | High |
| P2 | Delete schedule slot (#1) | Medium | Medium |
| P2 | Away/frost temp config (#3) | Medium | Medium |
| P3 | Anticipation control (#5) | Medium | Low |

---

## Unused API Endpoints

```
DELETE https://connect.intuis.net/api/deletenewhomeschedule
POST   https://connect.intuis.net/api/updatenewhomeschedule
```

---

## Data Available but Not Exposed

From `/syncapi/v1/homestatus`:
- `muller_type` - Device hardware type (partially exposed via sensor)

From `/api/homesdata`:
- RF signal strength (if available)

---

*Last updated: 2026-01-03*
