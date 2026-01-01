# Intuis Connect Integration - Architecture Overview

## System Components

### Cloud Infrastructure

The Intuis Connect system uses Netatmo's cloud infrastructure with multiple redundant clusters:

- **Primary**: `https://app.muller-intuitiv.net`
- **Secondary**: `https://app-prod.intuis-sas.com`
- **Energy API**: `https://connect.intuis.net/api`

### Hardware Hierarchy

```
Home (Mon domicile)
├── Gateway (NMG - IntuitivGateway)
│   └── WiFi connection to cloud
│
├── Room: Salon
│   ├── NMR Module (Radio transceiver) - f4:ce:36:xx:xx:xx
│   └── NMH Module (Heating module) - 00:00:00:00:xx:xx
│
├── Room: Chambre
│   ├── NMR Module
│   └── NMH Module
│
└── ... more rooms
```

### Communication Flow

```
Radiator (NMH) <--Zigbee--> Radio Module (NMR) <--Zigbee--> Gateway (NMG) <--WiFi--> Cloud API
```

## Home Assistant Integration Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    Home Assistant                                │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              DataUpdateCoordinator                        │   │
│  │                 (2 min interval)                          │   │
│  │  ┌────────────────────────────────────────────────────┐  │   │
│  │  │              IntuisData                             │  │   │
│  │  │  - async_update()                                   │  │   │
│  │  │  - _fetch_energy_data()                             │  │   │
│  │  │  - sticky override management                       │  │   │
│  │  └────────────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    IntuisAPI                              │   │
│  │  - Token management (access/refresh)                      │   │
│  │  - Retry logic with exponential backoff                   │   │
│  │  - Multi-cluster failover                                 │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
└──────────────────────────────┼───────────────────────────────────┘
                               │ HTTPS
                               ▼
                    ┌─────────────────────┐
                    │   Intuis Cloud API  │
                    └─────────────────────┘
```

## Entity Structure

### Per Room Entities

| Entity Type | Class | Description |
|-------------|-------|-------------|
| Climate | `IntuisClimate` | HVAC control (heat/off, presets) |
| Temperature Sensor | `IntuisTemperatureSensor` | Current room temperature |
| Target Temperature Sensor | `IntuisTargetTemperatureSensor` | Setpoint temperature |
| Energy Sensor | `IntuisEnergySensor` | Daily energy consumption (kWh) |
| Minutes Sensor | `IntuisMinutesSensor` | Heating minutes today |
| Muller Type Sensor | `IntuisMullerTypeSensor` | Device type identifier |
| Setpoint End Time Sensor | `IntuisSetpointEndTimeSensor` | Override expiration |
| Heating Binary Sensor | `IntuisHeatingBinarySensor` | Active heating state |
| Presence Binary Sensor | `IntuisPresenceBinarySensor` | Room presence detection |
| Window Binary Sensor | `IntuisOpenWindowBinarySensor` | Open window detection |

### Per Home Entities

| Entity Type | Description |
|-------------|-------------|
| Outdoor Temperature | From gateway's outdoor sensor |
| WiFi Strength | Gateway WiFi signal |
| Various config sensors | Home-level settings |

## Data Flow

1. **Coordinator Update** (every 2 minutes):
   - Fetch home status (`/syncapi/v1/homestatus`)
   - Fetch home config (`/syncapi/v1/getconfigs`)
   - Extract modules and rooms via mapper
   - Fetch energy data (after 2 AM, cached daily)
   - Re-apply sticky overrides if needed

2. **Control Commands**:
   - Climate entity calls `async_set_room_state()`
   - API sends to `/syncapi/v1/setstate`
   - Coordinator refreshes on next cycle

## Key Files

| File | Purpose |
|------|---------|
| `__init__.py` | Integration setup, coordinator creation |
| `intuis_api/api.py` | API client with auth and endpoints |
| `intuis_api/mapper.py` | Transform API data to entities |
| `intuis_data.py` | Data coordinator logic |
| `climate.py` | Climate entity implementation |
| `sensor.py` | All sensor entities |
| `binary_sensor.py` | Binary sensor entities |
| `entity/intuis_*.py` | Data classes for rooms, modules, home |
