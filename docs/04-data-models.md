# Data Models

## Python Classes

### IntuisHome

Represents the home configuration from `/api/homesdata`.

**File**: `entity/intuis_home.py`

```python
class IntuisHome:
    id: str                              # Home ID
    name: str                            # "Mon domicile"
    timezone: str                        # "Europe/Paris"
    rooms: dict[str, IntuisRoomDefinition]  # Room definitions
    schedules: list[IntuisSchedule]      # Weekly schedules
```

### IntuisRoomDefinition

Static room configuration from homesdata.

**File**: `entity/intuis_room.py`

```python
class IntuisRoomDefinition:
    id: str                    # Room ID
    name: str                  # "Salon"
    type: str                  # "livingroom", "bedroom", etc.
    module_ids: list[str]      # Assigned NMH module IDs
    modules: list[dict]        # Module details
    therm_relay: dict | None   # Relay configuration
```

### IntuisRoom

Live room state from `/syncapi/v1/homestatus`.

**File**: `entity/intuis_room.py`

```python
class IntuisRoom:
    definition: IntuisRoomDefinition
    id: str
    name: str
    mode: str                    # "home", "away", "manual", "boost", "off"
    target_temperature: float    # Setpoint in °C
    temperature: float           # Measured temperature in °C
    presence: bool               # Presence detected
    open_window: bool            # Window open detected
    anticipation: bool           # Anticipation mode active
    muller_type: str             # "FPN", "IOT"
    boost_status: str            # "disabled", "enabled"
    modules: list[IntuisModule]  # Associated modules
    therm_setpoint_end_time: int # Override expiry (Unix timestamp)
    bridge_id: str | None        # Gateway MAC for energy queries

    # Computed/tracked fields:
    heating: bool = False        # Currently heating
    minutes: int = 0             # Heating minutes today
    energy: float = 0.0          # Daily energy consumption (kWh)
```

### IntuisModule

Module information from homestatus.

**File**: `entity/intuis_module.py`

```python
class IntuisModule:
    id: str                      # Module MAC
    type: str                    # "NMG", "NMR", "NMH"
    bridge: str | None           # Parent gateway MAC
    firmware_revision: int | None
    last_seen: int | None        # Unix timestamp
    reachable: bool

    # NMG-specific:
    wifi_strength: int | None
    outdoor_temperature: float | None

    # NMH-specific:
    muller_type: str | None
    radiator_state: str | None   # "heating", "idle"
    presence_sensor: bool
    offload: bool
```

### IntuisHomeConfig

Home configuration from `/syncapi/v1/getconfigs`.

**File**: `entity/intuis_home_config.py`

```python
class IntuisHomeConfig:
    # Contains various home-level settings
    # Used for home-level sensor entities
```

### IntuisSchedule

Weekly heating schedule.

**File**: `entity/intuis_schedule.py`

```python
class IntuisSchedule:
    id: int
    name: str
    selected: bool               # Currently active schedule
    slots: list[IntuisSlot]      # Time slots
```

## Coordinator Data Structure

The `DataUpdateCoordinator` returns this structure on each update:

```python
{
    "id": str,                           # Home ID
    "home_id": str,                      # Same as id
    "home_config": IntuisHomeConfig,     # Config data
    "rooms": dict[str, IntuisRoom],      # Room ID -> IntuisRoom
    "modules": list[IntuisModule],       # All modules
    "intuis_home": IntuisHome,           # Home definition
    "schedules": list[IntuisSchedule],   # Schedules
}
```

## State Management

### Sticky Overrides

The integration maintains sticky overrides for temperature control:

```python
self._overrides: dict[str, dict] = {
    "room_id": {
        "mode": "manual",
        "temp": 21.0,
        "end": 1767200000,    # Unix timestamp
        "sticky": True
    }
}
```

### Energy Cache

Daily energy data is cached to avoid repeated API calls:

```python
self._energy_cache: dict[str, float] = {
    "_date": "2025-12-31",    # Cache date
    "room_id_1": 2.5,         # kWh
    "room_id_2": 1.8,
}
```

### Minutes Counter

Heating minutes are tracked locally between updates:

```python
self._minutes_counter: dict[str, int] = {
    "room_id_1": 45,          # Minutes heated today
    "room_id_2": 30,
}
```

## Entity Base Classes

### IntuisEntity

Base class for room-level entities.

**File**: `entity/intuis_entity.py`

```python
class IntuisEntity(CoordinatorEntity):
    _room_id: str

    @property
    def room(self) -> IntuisRoom:
        return self.coordinator.data["rooms"][self._room_id]

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{home_id}_{room_id}")},
            name=room_name,
            manufacturer="Muller Intuitiv (Netatmo)",
            model="Electric Radiator",
        )
```

### IntuisHomeEntity

Base class for home-level entities.

**File**: `entity/intuis_home_entity.py`

```python
class IntuisHomeEntity(CoordinatorEntity):
    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{home_id}_home")},
            name="Intuis Home",
            manufacturer="Muller Intuitiv (Netatmo)",
            model="Home Controller",
        )
```
