# Supported devices

This list covers every Logix device the LogixDIY integration can set up, and what each one needs. Devices not listed here are refused during setup with "This Logix model is not supported yet".

| Device | Model ID | Minimum firmware | API version | Integration version | Status |
|---|---|---|---|---|---|
| [Logix 3](#logix-3): three-button RGB scene controller | `logix3` | 1.2.0 | 1 | 1.0.0 | Supported |

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

## Adding a device

When a new Logix device is ready:

1. Its firmware uses `BaseCore`, so it advertises `_logix._tcp`, serves `GET /api/info` and publishes `logix/discovery/<id>`.
2. Register its model ID in [`custom_components/logixdiy/models.py`](custom_components/logixdiy/models.py), with its display name and entity platforms.
3. If its controls differ from the Logix 3's (buttons and RGB LEDs), add the platform code for them.
4. Add tests with sample `/api/info` and state responses from the real firmware.
5. Add a row to the table above and a section for the device, then bump `version` in [`manifest.json`](custom_components/logixdiy/manifest.json).
