# Intuis Connect API Reference

## Base URLs

| Purpose | URL |
|---------|-----|
| Primary API | `https://app.muller-intuitiv.net` |
| Fallback API | `https://app-prod.intuis-sas.com` |
| Energy/Schedule API | `https://connect.intuis.net/api` |

## Authentication

### OAuth2 Token Endpoint

**POST** `/oauth2/token`

#### Login (Password Grant)

```json
{
  "grant_type": "password",
  "username": "user@email.com",
  "password": "password",
  "client_id": "59e604638fe283fd4dc7e353",
  "client_secret": "ZW2vL8czEkn87zemtR1h1ZB0ZVwoeR",
  "scope": "read_muller write_muller",
  "user_prefix": "muller",
  "app_version": "1108100"
}
```

#### Token Refresh

```json
{
  "grant_type": "refresh_token",
  "refresh_token": "<refresh_token>",
  "client_id": "59e604638fe283fd4dc7e353",
  "client_secret": "ZW2vL8czEkn87zemtR1h1ZB0ZVwoeR",
  "user_prefix": "muller"
}
```

#### Response

```json
{
  "access_token": "...",
  "refresh_token": "...",
  "expires_in": 10800
}
```

## Data Endpoints

### Get Homes Data

**GET** `/api/homesdata`

Returns home configuration including room definitions and module assignments.

#### Response Structure

```json
{
  "body": {
    "homes": [{
      "id": "home_id",
      "name": "Mon domicile",
      "timezone": "Europe/Paris",
      "rooms": [
        {
          "id": "room_id",
          "name": "Salon",
          "type": "livingroom",
          "module_ids": ["00:00:00:00:xx:xx:xx:xx"]
        }
      ],
      "modules": [
        {
          "id": "70:ee:50:xx:xx:xx",
          "type": "NMG",
          "name": "IntuitivGateway"
        }
      ],
      "schedules": [...]
    }]
  }
}
```

### Get Home Status

**POST** `/syncapi/v1/homestatus`

Returns live status of all modules and rooms.

#### Request

```json
{
  "home_id": "home_id"
}
```

#### Response Structure

```json
{
  "body": {
    "home": {
      "id": "home_id",
      "modules": [
        {
          "id": "module_id",
          "type": "NMG|NMR|NMH",
          "bridge": "gateway_id",
          "firmware_revision": 161,
          "last_seen": 1767195000,
          "reachable": true
        }
      ],
      "rooms": [
        {
          "id": "room_id",
          "therm_setpoint_mode": "home|away|manual|boost|off",
          "therm_setpoint_temperature": 19.0,
          "therm_measured_temperature": 18.5,
          "therm_setpoint_end_time": 0,
          "muller_type": "FPN",
          "presence": false,
          "open_window": false,
          "boost_status": "disabled"
        }
      ]
    }
  }
}
```

### Get Home Config

**POST** `/syncapi/v1/getconfigs`

Returns home configuration settings.

#### Request

```json
{
  "home_id": "home_id"
}
```

### Set Room State

**POST** `/syncapi/v1/setstate`

Controls room heating mode and temperature.

#### Request

```json
{
  "app_type": "app_muller",
  "app_version": "1108100",
  "home": {
    "id": "home_id",
    "timezone": "Europe/Paris",
    "rooms": [{
      "id": "room_id",
      "therm_setpoint_mode": "manual",
      "therm_setpoint_temperature": 21.0,
      "therm_setpoint_end_time": 1767200000
    }]
  }
}
```

#### Modes

| Mode | Description |
|------|-------------|
| `home` | Follow schedule (comfort) |
| `away` | Away/eco temperature |
| `manual` | Manual temperature override (requires temp + end_time) |
| `boost` | Boost heating |
| `off` | Frost protection only |

## Energy Measurement

### Get Home Measure

**POST** `/api/gethomemeasure`

Fetches energy consumption data.

#### Request (Room-Level)

```json
{
  "app_identifier": "app_muller",
  "home": {
    "id": "home_id",
    "rooms": [
      {
        "id": "room_id",
        "bridge": "gateway_mac",
        "type": "sum_energy_elec$0"
      }
    ]
  },
  "scale": "1day",
  "date_begin": 1767052800,
  "date_end": 1767139199
}
```

#### Response

```json
{
  "body": {
    "home": {
      "id": "home_id",
      "rooms": [
        {
          "id": "room_id",
          "measures": [[timestamp, value], ...],
          "bridge": "gateway_mac"
        }
      ]
    }
  },
  "status": "ok"
}
```

#### Scale Values

| Scale | Description |
|-------|-------------|
| `1day` | Daily aggregation |
| `1week` | Weekly aggregation |
| `1month` | Monthly aggregation |

#### Known Measure Types

| Type | Description |
|------|-------------|
| `sum_energy_elec$0` | Electrical energy sum |
| `temperature` | Temperature readings |

**Note**: Not all radiator types support energy measurement. FPN (Fil Pilote Numérique) radiators may not have built-in energy sensors.

## Schedule Management

### Get Schedule

**GET** `https://connect.intuis.net/api/gethomeschedule`

#### Parameters

- `home_id`: Home identifier
- `schedule_id`: Schedule identifier

### Sync Home Schedule

**POST** `/api/synchomeschedule`

Creates or updates a schedule. This is the primary endpoint for schedule modifications.

#### Request

```json
{
  "home_id": "home_id",
  "id": "schedule_id",
  "name": "Planning",
  "type": "therm",
  "timetable": [
    {"zone_id": 1, "m_offset": 0},
    {"zone_id": 6, "m_offset": 360}
  ],
  "zones": [
    {
      "id": 1,
      "name": "Night",
      "type": 1,
      "rooms_temp": [{"room_id": "123", "temp": 17}]
    }
  ],
  "away_temp": 12,
  "hg_temp": 7
}
```

**Important**:
- `m_offset` is minutes from Monday 00:00 (0-10079)
- Zones must use `rooms_temp` array (not `rooms`)
- Consecutive timetable entries cannot have the same `zone_id`

See [Schedule Management](07-schedule-management.md) for detailed documentation.

### Update Schedule

**POST** `https://connect.intuis.net/api/updatenewhomeschedule`

### Delete Schedule Slot

**DELETE** `https://connect.intuis.net/api/deletenewhomeschedule`

### Switch Active Schedule

**POST** `https://connect.intuis.net/api/switchhomeschedule`

## Error Handling

### HTTP Status Codes

| Code | Handling |
|------|----------|
| 200 | Success |
| 401 | Token expired - refresh and retry |
| 429 | Rate limited - exponential backoff |
| 5xx | Server error - retry with backoff |

### API Error Codes

```json
{
  "error": {
    "code": 21,
    "message": "Filter energy does not exists"
  }
}
```

| Code | Description |
|------|-------------|
| 10 | Argument(s) is(are) missing |
| 21 | Invalid filter/type parameter |
| 21 | two same consecutive zone_id in timetable |
| 21 | Cannot mix rooms and rooms_temp in zones |
| 31 | Device not found in home |

## Request Headers

All authenticated requests require:

```
Authorization: Bearer <access_token>
Content-Type: application/json
```

## Rate Limiting

- Default timeout: 20 seconds per request
- Retry on 429/5xx: 3 attempts with exponential backoff (1.5s, 3s, 6s)
- Token refresh: 60 seconds before expiry
