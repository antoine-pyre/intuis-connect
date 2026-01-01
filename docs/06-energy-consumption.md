# Energy Consumption - FIXED

## Summary

**Energy consumption now works!** The solution is to use `/api/getroommeasure` instead of `/api/gethomemeasure`.

Key findings:
- `/api/gethomemeasure` requires webapp/native app token level (not available to third-party)
- `/api/getroommeasure` works with third-party credentials
- Must use **form-encoded data** (not JSON)
- Must request **all tariff types** to capture consumption on any tariff

## Root Cause

According to Netatmo's API documentation and developer forums:

> "The `/gethomemeasure` endpoint is only available with a higher token level (webapp/native Netatmo app). It is not currently available to third-party token levels."

**Source**: [Netatmo Developer Forum](https://helpcenter.netatmo.com/hc/en-us/community/posts/19559698051474-API-getmeasure-change)

## APK Decompilation Findings

Decompiling the Intuis Connect APK revealed:

### API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `/api/gethomemeasure` | Home-level energy measures |
| `/api/getroommeasure` | Room-level energy measures |
| `/api/getmeasure` | Device/module-level measures |
| `/api/getappliancemeasure` | Appliance-level measures |

### Request Structure for `/api/gethomemeasure`

```json
{
  "home": {
    "id": "home_id",
    "modules": [
      {"id": "module_id", "bridge": "gateway_id", "type": "sum_energy_elec$0,sum_energy_elec$1"}
    ],
    "rooms": [
      {"id": "room_id", "bridge": "gateway_id", "type": "sum_energy_elec$0,sum_energy_elec$1"}
    ]
  },
  "scale": "1day",
  "date_begin": "1735603200",
  "date_end": "1735689600"
}
```

### Available Measure Types (from decompiled code)

**Sum types** (for aggregated data):
- `sum_energy_elec` - Total energy (all tariffs)
- `sum_energy_elec$0` - Energy tariff 0 (base)
- `sum_energy_elec$1` - Energy tariff 1 (off-peak)
- `sum_energy_elec$2` - Energy tariff 2
- `sum_energy_elec_heating` - Heating energy only
- `sum_energy_elec_hot_water` - Hot water energy
- `sum_energy_price`, `sum_energy_price$0`, `sum_energy_price$1`, `sum_energy_price$2` - Price values

**Instant types** (for real-time/interval data):
- `energy_elec`, `energy_elec$0`, `energy_elec$1`, `energy_elec$2`
- `energy_elec_heating`, `energy_elec_hot_water`

### Available Scales

| Scale | Value |
|-------|-------|
| Max resolution | `max` |
| 5 minutes | `5min` |
| 30 minutes | `30min` |
| 1 hour | `1hour` |
| 3 hours | `3hours` |
| 6 hours | `6hours` |
| 1 day | `1day` |
| 1 week | `1week` |
| 1 month | `1month` |

## Investigation Results

### API Endpoints Tested

| Endpoint | Result |
|----------|--------|
| `/api/gethomemeasure` with correct structure | Empty/null measures |
| `/api/getroommeasure` | "Invalid string arg" error |
| `/api/getmeasure` | No energy data returned |
| Temperature measures (`temperature`, `sp_temperature`) | **Works** |

### Credentials Tested

| Client ID | Description | Result |
|-----------|-------------|--------|
| `59e604638fe283fd4dc7e353` | Integration original | No energy data |
| `59e604948fe283fd4dc7e355` | Node-RED flow | No energy data |

Both authenticate successfully and can control devices, but **neither has access to energy consumption data**.

## Why the Official App Works

The official Intuis Connect app uses:
1. **Webapp token level** credentials embedded in the app
2. These have **higher API access** than third-party developer tokens
3. The same endpoints work, but only with the right token level

## Potential Solutions

### Option 1: Request API Access (Best)

Contact Muller/Netatmo to:
- Request `/gethomemeasure` access for this client_id
- Or request a new client_id with webapp token level

### Option 2: OAuth Web Flow (Possible)

Implement OAuth 2.0 authorization code flow instead of password grant:
- User authorizes through Netatmo's web interface
- May grant higher access level
- Requires redirect URI and user interaction

### Option 3: Estimated Consumption (Workaround)

Calculate energy from heating time and user-configured wattage:

```yaml
# configuration.yaml
intuis_connect:
  room_power:
    salon: 1500  # watts
    chambre: 1000
    bureau: 750
```

```python
# Calculation
kwh = (wattage * minutes_heated) / 60 / 1000
```

### Option 4: Use `/getroommeasure` (Documented for third-party)

According to Netatmo docs, `/getroommeasure` should be available to third-party developers:

```json
{
  "home_id": "home_id",
  "room_id": "room_id",
  "scale": "1day",
  "type": "sum_energy_elec$0",
  "date_begin": "1735603200",
  "date_end": "1735689600"
}
```

This needs further testing with the correct request format.

## Current Integration Status

The integration already has:
- Correct API endpoint: `/api/gethomemeasure`
- Correct request structure in `api.py:368-440`
- Energy sensor entity in `sensor.py`

But it returns empty data due to token level restrictions.

## Files Involved

| File | Purpose |
|------|---------|
| `intuis_api/api.py` | `async_get_energy_measures()` method |
| `sensor.py` | `IntuisEnergySensor` entity |
| `const.py` | `HOMEMEASURE_PATH = "/api/gethomemeasure"` |

## Next Steps

1. **Test `/getroommeasure`** with the documented third-party format
2. **Contact Muller/Netatmo** about enabling energy endpoint access
3. **Implement estimation** as a fallback solution
4. **Consider OAuth flow** if higher token access is needed

## Working Solution (Implemented)

### Endpoint

Use `/api/getroommeasure` with form-encoded data:

```python
form_data = {
    "home_id": home_id,
    "room_id": room_id,
    "scale": "1day",
    "type": "sum_energy_elec,sum_energy_elec$0,sum_energy_elec$1,sum_energy_elec$2",
    "date_begin": str(start_timestamp),
    "date_end": str(end_timestamp),
}

response = await session.post(
    f"{BASE_URL}/api/getroommeasure",
    headers={"Authorization": f"Bearer {token}"},
    data=form_data,  # Form-encoded, NOT JSON
)
```

### Response Format

```json
{
  "body": [
    {
      "beg_time": 1767265200,
      "value": [[null, null, 14245, 7694]]
    }
  ],
  "status": "ok"
}
```

Values correspond to requested types in order:
- `sum_energy_elec` - Total (often null)
- `sum_energy_elec$0` - Base tariff (heures pleines)
- `sum_energy_elec$1` - Off-peak tariff 1 (heures creuses)
- `sum_energy_elec$2` - Off-peak tariff 2

### Changes Made

1. **const.py**: Added `ROOMMEASURE_PATH` and `ENERGY_MEASURE_TYPES`
2. **api.py**: Rewrote `async_get_energy_measures()` to use new endpoint
3. **intuis_data.py**: Convert Wh to kWh for display

## References

- [Netatmo Energy API Documentation](https://dev.netatmo.com/apidocumentation/energy)
- [Netatmo API getmeasure discussion](https://helpcenter.netatmo.com/hc/en-us/community/posts/19559698051474-API-getmeasure-change)
- [Node-RED flow](https://flows.nodered.org/flow/3d7f77cef8a7c6aa4fc33e2dbf26f15e)
