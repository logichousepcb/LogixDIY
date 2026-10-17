<p align="center">
  <img src="images/logo.png" alt="LogixDIY logo" width="180">
</p>

<h1 align="center">LogixDIY for Home Assistant</h1>

<p align="center">
  A Home Assistant integration for Logix devices. It finds them on your network, then gives you their buttons, LEDs and settings as entities and automation triggers.
</p>

## Supported devices

| Device | Model ID | Firmware |
|---|---|---|
| Logix 3: three-button RGB scene controller | `logix3` | [logix3-firmware](https://github.com/logichousepcb/logix3-firmware) 1.2.0 or later (API version 1) |

See **[DEVICES.md](DEVICES.md)** for each device's requirements, entities and known limitations. More Logix devices will be added over time.

## Installation

### HACS

1. In HACS, open the menu (⋮) → **Custom repositories**.
2. Add `https://github.com/logichousepcb/LogixDIY` with type **Integration**.
3. Install **LogixDIY** and restart Home Assistant.

### Manual

Copy `custom_components/logixdiy` into the `custom_components` folder of your Home Assistant configuration directory, then restart Home Assistant.

## Setup

Devices are found automatically in two ways:

- **mDNS:** each device advertises `_logix._tcp`. It appears under **Settings → Devices & services → Discovered**.
- **MQTT:** if the device and Home Assistant share a broker, its retained `logix/discovery/<id>` message also triggers discovery.

To add one by hand, go to **Add integration → LogixDIY** and enter its IP address or hostname (e.g. `esp12f-e527.local`).

If the device has an admin password, you are asked for it. If you change the password later, Home Assistant asks for the new one.

## What you get (Logix 3)

<p align="center">
  <img src="images/device-page.png" alt="Home Assistant device page for a Logix 3, showing device info, LED light and state controls, LED brightness and recent activity" width="760">
</p>

| Entity | Count | Description |
|---|---|---|
| `event.<device>_button_N` | 3 | Fires `single`, `double`, `triple` or `hold` for every completed button action |
| `light.<device>_led_N` | 3 | RGB LED. On means it shows one of its action colors. The **effect** chooses which one, and changing the color edits that slot. Brightness is shared by all three LEDs. |
| `select.<device>_led_N_state` | 3 | `off`, `single`, `double`, `triple` or `hold`. Setting it never toggles. |
| `number.<device>_led_brightness` | 1 | Brightness of all LEDs, 0-100 % |
| `button.<device>_button_N_<action>` | 12 | Simulates a press, exactly like the physical button. **Disabled by default.** |
| `button.<device>_restart` | 1 | Restarts the device |
| `sensor.<device>_wi_fi_signal` | 1 | Wi-Fi RSSI (diagnostic) |
| `sensor.<device>_ip_address` | 1 | IP address (diagnostic, disabled by default) |

### Automations

Every button action is available three ways. Use whichever suits you:

- **Device trigger:** in the automation editor, pick the device and then a trigger such as *Button 2 pressed twice*.
- **Event entity:** trigger on a state change of `event.<device>_button_2` with attribute `event_type: double`.
- **Bus event:** `logixdiy_button_action` with data `device_id`, `button` (1-3) and `action`.

```yaml
triggers:
  - trigger: event
    event_type: logixdiy_button_action
    event_data:
      button: 1
      action: hold
actions:
  - action: light.turn_off
    target:
      area_id: living_room
```

### Changing the saved colors

The `logixdiy.set_led_colors` action sets any of an LED's five colors without changing which one it shows:

```yaml
action: logixdiy.set_led_colors
target:
  entity_id: light.logix_3_e527_led_1
data:
  single_color: [255, 64, 64]
  hold_color: [128, 0, 255]
  off_color: [0, 0, 0]
```

## How it talks to the device

- **Commands** always go over the device's HTTP API.
- **State and button actions** are pushed over MQTT when the device has MQTT enabled and Home Assistant's MQTT integration is connected to the same broker. Polling then drops to once a minute, only to resync and read diagnostics.
- **Without MQTT,** the integration polls `GET /api/controller` every second, and detects button actions from changes in each button's `actionCount`. If a button completes several actions between two polls, only the last one is reported. Set a shorter interval, or use MQTT, if that matters for you.

Both settings live under **Configure** on the integration: MQTT on or off, and the poll interval (0.5-60 s).

## Adding another Logix device

The integration is built so that new Logix models slot in:

1. Every Logix firmware built on `BaseCore` already advertises `_logix._tcp`, serves `/api/info` and publishes `logix/discovery/<id>`. Discovery and setup work unchanged.
2. Register the model in [`models.py`](custom_components/logixdiy/models.py) with its display name and platforms.
3. Entities are built from the `capabilities` block of `/api/info` (the number of buttons and LEDs, actions, LED states, brightness). A device with the same kind of controls needs no new entity code. A device with different hardware (a motor, a sensor) gets its own platform module, which reads its own state.

A device whose `/api/info` reports an `api` version above 1 is refused, so a firmware change that breaks the API can't half-work.

## Development

Tests use [pytest-homeassistant-custom-component](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component):

```sh
pip install -r requirements_test.txt
pytest tests
```
