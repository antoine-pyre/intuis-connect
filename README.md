# Intuis Connect (Netatmo) – Home Assistant Integration

> Control and monitor **Muller / Campa / Intuis electric radiators** fitted with Netatmo “Intuitiv” modules – right from Home Assistant.


## Features

* **Auto-discovery** of every radiator (grouped by room)  
* **Climate entity** per room  
  * Schedule / Manual / Frost modes  
  * Presets : **Boost** and **Away** (durations & temperatures not configurable, they are set in the Intuis app)
* **Sensors**  
  * Temperature, Set-point
  * Presence & Open-window detection  (Not really useful, the integration pull the data every N minutes, so it’s not real-time)

---

## Installation (via HACS)

> **Requires Home Assistant 2024.6 or newer and HACS ≥ 1.33**

#### With HACS
[![Open your Home Assistant instance and add a repository in the Home Assistant Community Store (HACS).](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=antoine-pyre&repository=intuis-connect&category=integration)

More information [here](https://hacs.xyz/).

1. ### Add the custom repository  
   1. In Home Assistant, open **HACS ▸ Integrations**  
   2. Click **⋮ Custom repositories** (upper right)  
   3. URL :  
      ```
      https://github.com/antoine-pyre/homeassistant-intuis_connect
      ```  
      Category : **Integration** → **Add**

2. ### Download the integration  
   *Back in HACS ▸ Integrations* → search **“Intuis Connect”** → **Download** → **Restart** HA when prompted.

3. ### Configure  
   *Settings ▸ Devices & Services ▸ + Add Integration* → search **Intuis Connect (Netatmo)**  
   Enter the **email & password** you use in the Intuis mobile app → *Submit*.

That’s it – a device is created for each room with sensors **and** a fully-functional **Climate** entity.

---

## Dashboard quick-start

| Card type | What it gives you |
|-----------|------------------|
| **Thermostat** *(built-in)* | Slider for manual temperature, mode selector, presets in the More-Info dialog |
| **Button** | Create one-tap shortcuts &nbsp;→ `climate.set_preset_mode` (`boost`, `away`) |
| **Mushroom Climate** | Compact card with mode icons + preset menu (needs the [Mushroom](https://github.com/piitaya/lovelace-mushroom) add-on) |

Example Boost button:

```yaml
type: button
icon: mdi:fire
name: Boost 30 min
tap_action:
  action: call-service
  service: climate.set_preset_mode
  target: {entity_id: climate.living_room}
  data: {preset_mode: boost}
