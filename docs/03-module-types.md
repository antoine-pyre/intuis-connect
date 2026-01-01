# Intuis Module Types

## Overview

The Intuis Connect system uses a hierarchy of modules to control heating:

```
NMG (Gateway) ──► NMR (Radio) ──► NMH (Heater)
    │                 │               │
    │                 │               └── Physical radiator
    │                 └── ZigBee transceiver
    └── WiFi bridge to cloud
```

## NMG - Netatmo Gateway

The central hub that connects the heating system to the cloud.

### Identification

- **MAC format**: `70:ee:50:xx:xx:xx`
- **Type**: `NMG`
- **Name**: `IntuitivGateway`

### Capabilities

| Feature | Description |
|---------|-------------|
| WiFi | Cloud connectivity |
| ZigBee | Communication with NMR modules |
| Outdoor Temperature | Built-in or connected sensor |
| Schedule Limits | Max schedules/slots |

### API Fields (homesdata)

```json
{
  "id": "70:ee:50:49:10:25",
  "type": "NMG",
  "name": "IntuitivGateway",
  "subtype": "...",
  "setup_date": 1728470000,
  "reachable": true,
  "modules_bridged": ["list of bridged module IDs"],
  "schedule_limits": {...},
  "capabilities": [...]
}
```

### API Fields (homestatus)

```json
{
  "id": "70:ee:50:49:10:25",
  "type": "NMG",
  "firmware_revision": 161,
  "hardware_version": "...",
  "wifi_strength": 80,
  "outdoor_temperature": 5.0,
  "uptime": 123456,
  "configure": false,
  "debug_enabled": false,
  "open_zigbee": false,
  "router_id": "...",
  "therm_setpoint_day_color_type": "...",
  "therm_setpoint_default_duration": 120
}
```

## NMR - Netatmo Radio Module

ZigBee transceiver module that communicates between gateway and heaters.

### Identification

- **MAC format**: `f4:ce:36:xx:xx:xx:xx:xx` or `b0:02:7e:xx:xx:xx:xx:xx`
- **Type**: `NMR`
- **Name**: None (unnamed)

### Role

- Acts as ZigBee radio relay
- Bridges communication between NMG and NMH
- Each NMR is paired with one NMH module

### API Fields (homesdata)

```json
{
  "id": "f4:ce:36:3d:a7:70:6b:5e",
  "type": "NMR",
  "setup_date": 1728470000,
  "bridge": "70:ee:50:49:10:25"
}
```

### API Fields (homestatus)

```json
{
  "id": "f4:ce:36:3d:a7:70:6b:5e",
  "type": "NMR",
  "bridge": "70:ee:50:49:10:25",
  "firmware_revision": 33554435,
  "last_seen": 1767195000,
  "image_type": "...",
  "manufacturer_id": "..."
}
```

## NMH - Netatmo Heating Module

The logical representation of a physical radiator.

### Identification

- **MAC format**: `00:00:00:00:xx:xx:xx:xx`
- **Type**: `NMH`
- **Name**: User-defined (e.g., "Radiateur Salon 1")

### Association

Each NMH is:
- Assigned to exactly one room
- Connected via one NMR radio module
- Bridged through the NMG gateway

### API Fields (homesdata)

```json
{
  "id": "00:00:00:00:a7:70:6b:5e",
  "type": "NMH",
  "name": "Radiateur Salon 1",
  "setup_date": 1728470000,
  "room_id": "3327156261",
  "bridge": "70:ee:50:49:10:25",
  "muller_type": "FPN",
  "router_id": "f4:ce:36:3d:a7:70:6b:5e"
}
```

### API Fields (homestatus)

```json
{
  "id": "00:00:00:00:a7:70:6b:5e",
  "type": "NMH",
  "bridge": "70:ee:50:49:10:25",
  "last_seen": 1767195000,
  "reachable": true,
  "muller_type": "FPN",
  "radiator_state": "heating|idle",
  "offload": false,
  "presence_sensor": true,
  "router_id": "f4:ce:36:3d:a7:70:6b:5e",
  "firmware_revision_thirdparty": "..."
}
```

## Muller Types

The `muller_type` field indicates the radiator technology:

| Type | Full Name | Description |
|------|-----------|-------------|
| **FPN** | Fil Pilote Numérique | Digital pilot wire - standard French electric radiator protocol |
| **IOT** | IoT Native | Native IoT-connected radiators with more features |

### FPN (Fil Pilote Numérique)

- Standard French heating control protocol
- Uses 6 operating modes via pilot wire signal
- May not have built-in energy metering
- Common in retrofit installations

### Module Relationships

```
Room: Salon (ID: 3327156261)
│
├── NMH: 00:00:00:00:a7:70:6b:5e (Radiateur Salon 1)
│   ├── muller_type: FPN
│   ├── router_id: f4:ce:36:3d:a7:70:6b:5e (its NMR)
│   └── bridge: 70:ee:50:49:10:25 (gateway)
│
└── NMR: f4:ce:36:3d:a7:70:6b:5e
    └── bridge: 70:ee:50:49:10:25 (gateway)
```

## ID Relationships

| Module Type | ID Example | Notes |
|-------------|------------|-------|
| NMG | `70:ee:50:49:10:25` | Gateway MAC |
| NMR | `f4:ce:36:3d:a7:70:6b:5e` | Radio module MAC |
| NMH | `00:00:00:00:a7:70:6b:5e` | Virtual ID (last 4 bytes match NMR) |
| Room | `3327156261` | Numeric room ID |

The NMH ID appears to be derived from its paired NMR module - the last 4 bytes of both IDs match.
