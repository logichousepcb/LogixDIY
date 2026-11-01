# Supported devices

This list covers every Logix device the LogixDIY integration can set up, and what each one needs. Devices not listed here are refused during setup with "This Logix model is not supported yet".

| Device | Model ID | Minimum firmware | API version | Integration version | Status |
|---|---|---|---|---|---|
| [Logix 3](#logix-3): three-button RGB scene controller | `logix3` | 1.2.0 | 1 | 1.0.0 | Supported |
| [Logix Vent](#logix-vent): motorised vent controller | `logixvent` | 1.2.0 | 1 | 1.1.0 | Supported |
| [Logix Outlet](#logix-outlet): in-wall duplex receptacle with energy monitoring | `logixoutlet` | 1.0.0 | 1 | 1.2.0 | Supported |
| [Logix Plug](#logix-plug): plug-in smart plug, one outlet | `logixplug` | 1.0.0 | 1 | 1.3.0 | Supported |

**Model ID** is the `model` value the device reports in its mDNS TXT record and at `GET /api/info`. **API version** is the `api` value there. The integration refuses a device that reports a newer API version than it understands.

## Logix 3

A three-button scene controller for a standard Decora wall plate, built on an ESP8266 (ESP-12F). Each button has its own RGB LED, and each button recognizes single, double and triple presses and a 3-second hold.

- **Hardware:** [Multi-Button-WS2812-RGB-esp8266-Decora](https://github.com/logichousepcb/Multi-Button-WS2812-RGB-esp8266-Decora)
- **Firmware:** [logix3-firmware](https://github.com/logichousepcb/logix3-firmware), version 1.2.0 or later

Older firmware for the same hardware, such as the ESPHome configuration or the `logix_three_button` firmware, does not provide the Logix API and won't work with this integration. Use ESPHome's own integration for those builds.

### Discovery

| Method | Requirement |
|---|---|
| mDNS (`_logix._tcp`) | Device and Home Assistant on the same network segment |
| MQTT (`logix/discovery/<id>`) | MQTT enabled on the device, using the same broker as Home Assistant's MQTT integration |
| Manual | Device IP address or hostname |

### Entities

| Entity | Count | Notes |
|---|---|---|
| Event: Button 1-3 | 3 | Fires `single`, `double`, `triple` or `hold` |
| Light: LED 1-3 | 3 | Effect chooses which saved color is shown. Brightness is shared by all three LEDs. |
| Select: LED 1-3 state | 3 | `off`, `single`, `double`, `triple`, `hold` |
| Number: LED brightness | 1 | 0-100 % |
| Button: Button 1-3 single / double / triple press, hold | 12 | Simulates the physical button. Disabled by default. |
| Button: Restart | 1 | |
| Sensor: Wi-Fi signal | 1 | Diagnostic |
| Sensor: IP address | 1 | Diagnostic. Disabled by default. |

Also: device triggers for each button and action, the `logixdiy_button_action` bus event, and the `logixdiy.set_led_colors` action.

### Known limitations

- Without MQTT, button actions are detected by polling (every second by default). If a button completes several actions between two polls, only the last one is reported.
- An LED whose off color is not black still glows while Home Assistant shows its light as off.

## Logix Vent

A motorised vent controller built on an ESP8266 (ESP-01 class, 1 MB flash). It drives the vent motor one way or the other for a fixed 10 seconds, has a push button that toggles the vent, and a WS2811 RGB status light that turns red while opening and green while closing.

- **Firmware:** [vent-controller-firmware](https://github.com/logichousepcb/vent-controller-firmware), version 1.2.0 or later. It installs over the web page OTA form of a board still running the original ESPHome configuration.

The firmware also keeps the ESPHome native API, so the device can be set up through ESPHome's own integration as well. Use one or the other. With both, every entity appears twice.

### Discovery

| Method | Requirement |
|---|---|
| mDNS (`_logix._tcp`) | Device and Home Assistant on the same network segment |
| Manual | Device IP address or hostname, e.g. `basementvent.local` |

The firmware has no MQTT, so the state is polled (every second by default).

### Entities

| Entity | Count | Notes |
|---|---|---|
| Cover: vent | 1 | Damper. Open, close, stop. Shows opening or closing while the motor runs, with `remaining_ms` as an attribute. |
| Light: Status light | 1 | RGB with brightness, transitions and the effects `pulse` and `fast_pulse` |
| Event: Button 1 | 1 | Fires `single` when the physical button is pressed |
| Button: Button 1 single press | 1 | Same as pressing the physical button: toggles the vent. Disabled by default. |
| Button: Restart | 1 | |
| Sensor: Wi-Fi signal | 1 | Diagnostic |
| Sensor: IP address | 1 | Diagnostic. Disabled by default. |

Also: a device trigger "Button 1 pressed once" and the `logixdiy_button_action` bus event.

### Known limitations

- The vent has no position sensor. Its open or closed state is where it was last driven, and it is not corrected if the vent is moved by hand.
- A press of the physical button is only detected on the next poll. If it is pressed several times between two polls, one event fires.
- `logixdiy.set_led_colors` does not apply to the status light; use `light.turn_on`.

## Logix Outlet

Replacement firmware for the Gosund WO1 in-wall duplex receptacle (ESP8285, 1 MB). It has two independently switched outlets, one button for each, and a BL0937 energy meter that measures both outlets together.

- **Firmware:** [logix-outlet-firmware](https://github.com/logichousepcb/logix-outlet-firmware), version 1.0.0 or later. Install it over Tasmota's web OTA form with the gzipped image.

### Discovery

| Method | Requirement |
|---|---|
| mDNS (`_logix._tcp`) | Device and Home Assistant on the same network segment |
| MQTT (`logix/discovery/<id>`) | MQTT enabled on the device, using the same broker as Home Assistant's MQTT integration |
| Manual | Device IP address or hostname, e.g. `family-room-outlet.local` |

### Entities

| Entity | Count | Notes |
|---|---|---|
| Switch: Top, Bottom | 2 | The outlets. Device class `outlet`. |
| Sensor: Voltage, Current, Power | 3 | Energy meter, both outlets combined |
| Sensor: Apparent power, Reactive power, Power factor | 3 | Disabled by default |
| Sensor: Energy today, Energy yesterday, Energy total | 3 | kWh. Energy total is `total_increasing`, for the Energy dashboard. |
| Event: Button 1-2 | 2 | Fires `single`. Button 1 is the top button. |
| Button: Button 1-2 single press | 2 | Toggles that outlet like the physical button. Disabled by default. |
| Button: Restart | 1 | |
| Sensor: Wi-Fi signal | 1 | Diagnostic |
| Sensor: IP address | 1 | Diagnostic. Disabled by default. |

Also: device triggers "Button 1 pressed once" and "Button 2 pressed once", and the `logixdiy_button_action` bus event.

### Known limitations

- One meter measures both outlets, so there is no per-outlet power.
- The energy readings are only as accurate as the device's calibration. Calibrate it on the device's own settings page.
- The outlets switch off for about 10 s while the device installs a firmware update.

## Logix Plug

Replacement firmware for the Geekbes YM-WS-1 plug-in smart plug (ESP8266EX, 1 MB). It has one switched outlet, one button that toggles it, and one LED. It has no energy meter.

- **Firmware:** [logix-plug-firmware](https://github.com/logichousepcb/logix-plug-firmware), version 1.0.0 or later. Install it over Tasmota's web OTA form with the gzipped image.

### Discovery

| Method | Requirement |
|---|---|
| mDNS (`_logix._tcp`) | Device and Home Assistant on the same network segment |
| MQTT (`logix/discovery/<id>`) | MQTT enabled on the device, using the same broker as Home Assistant's MQTT integration |
| Manual | Device IP address or hostname, e.g. `entry-table-lamp.local` |

### Entities

| Entity | Count | Notes |
|---|---|---|
| Switch (named after the device) | 1 | The outlet. Device class `outlet`. |
| Event: Button 1 | 1 | Fires `single` |
| Button: Button 1 single press | 1 | Toggles the plug like the physical button. Disabled by default. |
| Button: Restart | 1 | |
| Sensor: Wi-Fi signal | 1 | Diagnostic |
| Sensor: IP address | 1 | Diagnostic. Disabled by default. |

Also: the device trigger "Button 1 pressed once", and the `logixdiy_button_action` bus event.

### Known limitations

- No energy monitoring: the hardware has no meter.
- The plug switches off for about 10 s while the device installs a firmware update.

## Adding a device

When a new Logix device is ready:

1. Its firmware uses `BaseCore`, so it advertises `_logix._tcp`, serves `GET /api/info` and publishes `logix/discovery/<id>`.
2. Register its model ID in [`custom_components/logixdiy/models.py`](custom_components/logixdiy/models.py), with its display name, entity platforms and the class that parses its `/api/controller` state.
3. If its controls differ from the Logix 3's (buttons and RGB LEDs), add a state class in `api.py` and the platform code for them, as the Logix Vent does with `VentState`, `cover.py` and its status light.
4. Add tests with sample `/api/info` and state responses from the real firmware.
5. Add a row to the table above and a section for the device, then bump `version` in [`manifest.json`](custom_components/logixdiy/manifest.json).
