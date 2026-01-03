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
- `switch_schedule`, `set_schedule_slot`, `refresh_schedules`, `set_zone_temperature`

---

## Missing Features

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

### 2. Home-Level Energy Aggregation Sensor

**Interest:**
Currently only room-level energy sensors exist. Users wanting total home consumption must create template sensors manually. A native sensor simplifies energy dashboard setup and tracking.

**Requirements:**
- API endpoint: `POST /api/gethomemeasure` (already available)
- Change: Query at home level instead of room level
- Data: `sum_energy_elec` aggregated across all rooms

**HA Integration:**
- New sensor entity: `sensor.intuis_home_energy`
- Add to `sensor.py` alongside room energy sensors
- Include in energy dashboard auto-discovery
- State class: `total_increasing`, device class: `energy`

---

### 3. Tariff-Separated Energy Sensors

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

---

### 4. Module/Gateway Health Sensors

**Interest:**
Hardware issues (disconnected gateway, unreachable radiator module) are invisible to users until heating fails. Proactive monitoring enables alerts before comfort is impacted.

**Requirements:**
- Data source: `/api/homesdata` contains module info
- Fields: `reachable`, `last_seen`, `firmware`, `rf_strength` (if available)
- No additional API calls needed - data already fetched

**HA Integration:**
- New binary sensors: `binary_sensor.{module}_reachable`
- New sensors: `sensor.{module}_last_seen`, `sensor.{module}_firmware`
- Device class: `connectivity` for reachability
- Group under gateway device in HA device registry
- Optional: Diagnostic sensors (hidden by default)

---

### 5. Boost Status Binary Sensor

**Interest:**
Boost mode is a common heating feature but currently only visible through the climate preset. A dedicated binary sensor enables simpler automations and better visibility in dashboards.

**Requirements:**
- Data source: `boost_status` field in `/syncapi/v1/homestatus`
- Already fetched during coordinator updates
- No additional API calls needed

**HA Integration:**
- New binary sensor: `binary_sensor.{room}_boost_active`
- Device class: `running` or `heat`
- Add attributes: `boost_end_time` if available
- Use for automation triggers (e.g., notify when boost ends)

---

### 6. Home Presence Aggregation Sensor

**Interest:**
Each room has a presence sensor, but users often need "is anyone home" logic. Currently requires template sensors combining all room presence states. A native sensor simplifies automations.

**Requirements:**
- Data source: Existing room presence data
- Logic: OR operation across all room `presence` values
- No additional API calls needed

**HA Integration:**
- New binary sensor: `binary_sensor.intuis_home_presence`
- Device class: `occupancy`
- Attributes: List of occupied rooms, count of occupied rooms
- Attach to home device, not individual rooms

---

### 7. Batch Room Control Service

**Interest:**
Setting multiple rooms to the same mode (e.g., all to away mode) requires multiple service calls. The API supports arrays of rooms in a single request, reducing latency and API load.

**Requirements:**
- API endpoint: `POST /syncapi/v1/setstate` (already used)
- Change: Build payload with multiple room entries
- Validate all rooms before sending

**HA Integration:**
- New service: `intuis_connect.set_rooms_state`
- Schema: `rooms` (list), `mode`, `temperature` (optional), `duration` (optional)
- Alternative: `intuis_connect.set_home_mode` for all rooms at once
- Reduces API calls from N to 1 for bulk operations

---

### 8. Away/Frost Temperature Configuration

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

### 9. Schedule Duplication Service

**Interest:**
Creating seasonal schedules (summer/winter) or backup schedules requires manual recreation. Duplicating an existing schedule saves time and reduces errors.

**Requirements:**
- API endpoint: `POST /api/synchomeschedule`
- Logic: Fetch existing schedule, modify name/ID, POST as new
- No dedicated API endpoint - client-side duplication

**HA Integration:**
- New service: `intuis_connect.duplicate_schedule`
- Schema: `source_schedule`, `new_name`
- Generate new schedule ID client-side
- Refresh schedules after creation

---

### 10. Configurable Energy Reset Time

**Interest:**
Energy sensors reset daily at 2 AM (hardcoded). Users with different utility billing cycles (midnight, 6 AM) cannot align HA data with their bills accurately.

**Requirements:**
- No API change needed
- Modify `_check_daily_reset()` in `sensor.py`
- Store reset hour in config entry options

**HA Integration:**
- Add option in config flow: "Daily energy reset time"
- Default: 2:00 AM (current behavior)
- Range: 00:00 - 23:59
- Apply to all energy sensors for the integration

---

### 11. Historical Energy Export Service

**Interest:**
The API supports historical data queries with scales up to `1month`. Users analyzing long-term trends or migrating data cannot easily access historical consumption.

**Requirements:**
- API endpoint: `POST /api/getroommeasure` with custom date range
- Parameters: `date_begin`, `date_end`, `scale`
- Scales: `5min`, `30min`, `1hour`, `1day`, `1week`, `1month`

**HA Integration:**
- New service: `intuis_connect.get_energy_history`
- Schema: `room` (optional), `start_date`, `end_date`, `scale`
- Return: Fire event with data or save to file
- Alternative: Populate HA statistics database directly

---

### 12. Heating Efficiency Metrics

**Interest:**
Understanding heating efficiency (energy per degree, cost per hour) helps identify problems like poor insulation or malfunctioning equipment. Currently requires manual calculations.

**Requirements:**
- Data sources: `heating_minutes`, `energy` sensors, outdoor temperature (external)
- Logic: Calculate ratios and trends
- No additional API calls needed

**HA Integration:**
- New sensors: `sensor.{room}_heating_efficiency`
- Calculation: kWh per degree-hour or similar metric
- Requires outdoor temperature entity (configurable)
- State class: `measurement`
- Consider as optional/advanced feature

---

### 13. Anticipation Control

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

### 14. Rate Limit Status Attributes

**Interest:**
Heavy automation usage can hit API rate limits. Exposing remaining quota helps users tune polling intervals and avoid service disruptions.

**Requirements:**
- Check API response headers for rate limit info
- Common headers: `X-RateLimit-Remaining`, `X-RateLimit-Reset`
- Store values during each API call

**HA Integration:**
- Add attributes to integration diagnostics
- New sensor: `sensor.intuis_api_quota` (optional)
- Emit warning log when quota low
- Consider adaptive polling based on quota

---

### 15. Schedule Conflict Detection

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

### 16. Multi-Home Energy Aggregation

**Interest:**
Users with multiple properties (vacation home, rental) want combined energy tracking. Currently each home is independent with no cross-home views.

**Requirements:**
- Data source: Existing home-level data from each configured home
- Logic: Sum across homes
- No additional API calls needed

**HA Integration:**
- New sensor: `sensor.intuis_all_homes_energy`
- Only created when multiple homes configured
- Attributes: Breakdown per home
- Consider as optional feature in config flow

---

## Implementation Priority Matrix

| Priority | Feature | Effort | Impact |
|----------|---------|--------|--------|
| P1 | Home-level energy sensor | Low | High |
| P1 | Module health sensors | Low | High |
| P1 | Boost status binary sensor | Low | Medium |
| P1 | Home presence aggregation | Low | Medium |
| P2 | Tariff-separated energy | Medium | High |
| P2 | Batch room control | Medium | Medium |
| P2 | Delete schedule slot | Medium | Medium |
| P2 | Away/frost temp config | Medium | Medium |
| P3 | Configurable reset time | Low | Low |
| P3 | Schedule duplication | Medium | Low |
| P3 | Historical energy export | Medium | Medium |
| P3 | Anticipation control | Medium | Low |
| P4 | Heating efficiency metrics | High | Medium |
| P4 | Rate limit status | Low | Low |
| P4 | Schedule conflict detection | Medium | Low |
| P4 | Multi-home aggregation | Low | Low |

---

## Unused API Endpoints

```
DELETE https://connect.intuis.net/api/deletenewhomeschedule
POST   https://connect.intuis.net/api/updatenewhomeschedule
```

---

## Data Available but Not Exposed

From `/syncapi/v1/homestatus`:
- `last_seen` - Module last communication timestamp
- `muller_type` - Device hardware type
- `boost_status` - Boost mode active flag

From `/api/homesdata`:
- Module firmware versions
- Gateway connection status
- RF signal strength (if available)

---

*Generated: 2026-01-02*
