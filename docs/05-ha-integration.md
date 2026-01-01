# Home Assistant Integration

## Directory Structure

```
custom_components/intuis_connect/
├── __init__.py              # Integration setup
├── config_flow.py           # Configuration UI
├── climate.py               # Climate entities
├── sensor.py                # Sensor entities
├── binary_sensor.py         # Binary sensor entities
├── manifest.json            # Integration metadata
├── strings.json             # UI strings
├── translations/            # Localization
│
├── entity/                  # Data classes
│   ├── intuis_entity.py     # Base room entity
│   ├── intuis_home_entity.py # Base home entity
│   ├── intuis_home.py       # Home data class
│   ├── intuis_home_config.py
│   ├── intuis_module.py
│   ├── intuis_room.py
│   └── intuis_schedule.py
│
├── intuis_api/              # API client
│   ├── api.py               # HTTP client
│   └── mapper.py            # Data transformation
│
├── intuis_data.py           # Coordinator logic
│
└── utils/
    └── const.py             # Constants
```

## Setup Flow

### 1. Config Flow (`config_flow.py`)

User provides credentials → Login → Store tokens

```python
async def async_step_user(self, user_input):
    # Validate credentials
    api = IntuisAPI(session)
    home_id = await api.async_login(username, password)

    # Store in config entry
    return self.async_create_entry(
        title="Intuis Connect",
        data={
            CONF_HOME_ID: home_id,
            CONF_REFRESH_TOKEN: api.refresh_token,
        }
    )
```

### 2. Integration Setup (`__init__.py`)

```python
async def async_setup_entry(hass, entry):
    # 1. Initialize API
    api = IntuisAPI(session, home_id=entry.data["home_id"])
    api.refresh_token = entry.data[CONF_REFRESH_TOKEN]
    await api.async_refresh_access_token()

    # 2. Get home data
    intuis_home = await api.async_get_homes_data()

    # 3. Create data handler
    intuis_data = IntuisData(api, intuis_home, ...)

    # 4. Create coordinator
    coordinator = DataUpdateCoordinator(
        hass,
        update_method=intuis_data.async_update,
        update_interval=timedelta(minutes=2),
    )
    await coordinator.async_config_entry_first_refresh()

    # 5. Store runtime data
    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
        "intuis_home": intuis_home,
        "overrides": overrides,
    }

    # 6. Setup platforms
    await hass.config_entries.async_forward_entry_setups(
        entry, ["climate", "sensor", "binary_sensor"]
    )
```

### 3. Platform Setup

Each platform creates entities for all rooms:

```python
# sensor.py
async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    intuis_home = data["intuis_home"]

    entities = []
    for room_id, room in intuis_home.rooms.items():
        entities.append(IntuisTemperatureSensor(coordinator, room_id))
        entities.append(IntuisEnergySensor(coordinator, room_id))
        # ... more sensors

    async_add_entities(entities)
```

## Update Cycle

Every 2 minutes, the coordinator:

```python
async def async_update(self) -> dict:
    # 1. Check for new day (reset counters)
    if is_new_day:
        self._minutes_counter.clear()
        self._energy_cache.clear()

    # 2. Fetch current state
    home = await self._api.async_get_home_status()
    config = await self._api.async_get_config()

    # 3. Process modules and rooms
    modules = extract_modules(home)
    rooms = extract_rooms(home, modules, ...)

    # 4. Re-apply sticky overrides if needed
    for room_id, override in self._overrides.items():
        if should_reapply(override):
            await self._api.async_set_room_state(...)

    # 5. Fetch energy data (after 2 AM)
    await self._fetch_energy_data(rooms, now)

    # 6. Return structured data
    return {
        "rooms": rooms,
        "modules": modules,
        "home_config": config,
        ...
    }
```

## Climate Entity

### HVAC Modes

| HA Mode | API Mode | Description |
|---------|----------|-------------|
| `heat` | `home` | Follow schedule |
| `off` | `off` | Frost protection |

### Presets

| Preset | API Mode | Behavior |
|--------|----------|----------|
| `schedule` | `home` | Follow schedule |
| `away` | `away` | Eco temperature |
| `boost` | `boost` | Maximum heating |

### Temperature Control

```python
async def async_set_temperature(self, **kwargs):
    temp = kwargs.get(ATTR_TEMPERATURE)
    await self._api.async_set_room_state(
        self._room_id,
        mode="manual",
        temp=temp,
        duration=self._manual_duration,
    )
    # Store as sticky override
    self._overrides[self._room_id] = {
        "mode": "manual",
        "temp": temp,
        "end": now + duration,
        "sticky": True,
    }
```

## Configuration Options

Editable via Options flow:

| Option | Default | Description |
|--------|---------|-------------|
| `manual_duration` | 5 min | Manual override duration |
| `away_duration` | 1440 min | Away mode duration |
| `boost_duration` | 30 min | Boost mode duration |
| `away_temp` | 16°C | Away mode temperature |
| `boost_temp` | 30°C | Boost mode temperature |
| `indefinite_mode` | False | Keep reapplying overrides |

## Sticky Overrides

The integration maintains temperature overrides even after the API timeout:

1. User sets temperature → API call with duration
2. Backend reverts after duration expires
3. Coordinator detects mismatch
4. Re-applies override automatically

With `indefinite_mode`:
- Override is re-applied 5 minutes before expiry
- Effectively creates "indefinite" manual mode

## Error Handling

### Token Refresh

```python
if response.status == 401:
    await self.async_refresh_access_token()
    return await self._async_request(...)  # Retry
```

### Retry Logic

- Network errors: 3 attempts with exponential backoff
- 5xx/429 errors: 3 attempts with backoff
- 4xx errors: Fail immediately

### Cluster Failover

On login failure:
```python
for base_url in BASE_URLS:
    try:
        response = await login(base_url)
        self._base_url = base_url  # Use this cluster
        break
    except:
        continue
```
