# Supported devices

This list covers every Logix device the LogixDIY integration can set up, and what each one needs. Devices not listed here are refused during setup with "This Logix model is not supported yet".

| Device | Model ID | Minimum firmware | API version | Integration version | Status |
|---|---|---|---|---|---|
| [Logix 3](#logix-3): three-button RGB scene controller | `logix3` | 1.2.0 | 1 | 1.0.0 | Supported |
| [Logix Vent](#logix-vent): motorised vent controller | `logixvent` | 1.2.0 | 1 | 1.1.0 | Supported |
| [Logix Outlet](#logix-outlet): in-wall duplex receptacle with energy monitoring | `logixoutlet` | 1.0.0 | 1 | 1.2.0 | Supported |
| [Logix Plug 3](#logix-plug-3): KMC 4 Outlet smart power strip, three switched outlets with energy monitoring | `logixplug3` | 1.0.0 | 1 | 1.7.0 | Supported |
| [Logix Energy Plug](#logix-energy-plug): AWP04L plug-in smart plug with energy monitoring | `logixenergyplug` | 1.0.0 | 1 | 1.8.0 | Supported |
| [Logix S31 Plug](#logix-s31-plug): Sonoff S31 plug-in smart plug with energy monitoring | `logixs31` | 1.0.0 | 1 | 1.10.0 | Supported |
| [Logix Plug](#logix-plug): plug-in smart plug, one outlet | `logixplug` | 1.0.0 | 1 | 1.3.0 | Supported |
| [Logix RGB Plug](#logix-rgb-plug): plug-in smart plug with an RGB night light | `logixrgbplug` | 1.0.0 | 1 | 1.4.0 | Supported |
| [Logix GR](#logix-gr): garage door relay with a button, RGB LED and temperature sensor | `logixgr` | 1.0.0 | 1 | 1.5.0 | Supported |
| [Logix RGB Switch](#logix-rgb-switch): KAUF SRF10 in-wall RGB light switch | `logixrgbswitch` | 1.0.0 | 1 | 1.6.0 | Supported |
| [Logix Temp](#logix-temp): Wemos D1 mini with a DS18B20 temperature sensor | `logixtemp` | 1.0.0 | 1 | 1.9.0 | Supported |
| [Logix 3-Way Switch](#logix-3-way-switch): Moes 3-way wall switch | `logix3way` | 1.0.0 | 1 | 1.10.0 | Supported |
| [Logix Fixture](#logix-fixture): ESP-12F addressable RGB LED strip/string controller with IR remote | `logixfixture` | 1.2.0 | 1 | 1.11.0 | Supported |

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

## Logix Plug 3

Replacement firmware for the KMC 4 Outlet smart power strip (ESP8266EX, 1 MB). It has three switched outlets (plus one that is always on), one button for all of them, and an HLW8012 energy meter that measures the whole strip.

- **Firmware:** [logix-plug3-firmware](https://github.com/logichousepcb/logix-plug3-firmware), version 1.0.0 or later. Install it over Tasmota's web OTA form with the gzipped image.

### Discovery

| Method | Requirement |
|---|---|
| mDNS (`_logix._tcp`) | Device and Home Assistant on the same network segment |
| MQTT (`logix/discovery/<id>`) | MQTT enabled on the device, using the same broker as Home Assistant's MQTT integration |
| Manual | Device IP address or hostname, e.g. `garage-4-outlet.local` |

### Entities

| Entity | Count | Notes |
|---|---|---|
| Switch: Outlet 1-3 | 3 | The outlets. Device class `outlet`. |
| Sensor: Voltage, Current, Power | 3 | Energy meter, whole strip |
| Sensor: Apparent power, Reactive power, Power factor | 3 | Disabled by default |
| Sensor: Energy today, Energy yesterday, Energy total | 3 | kWh. Energy total is `total_increasing`, for the Energy dashboard. |
| Event: Button 1 | 1 | Fires `single`, `double`, `triple` or `hold` |
| Button: Button 1 single / double / triple press, hold | 4 | Act like the physical button: toggle outlet 1, 2 or 3, or switch all. Disabled by default. |
| Button: Restart | 1 | |
| Sensor: Wi-Fi signal | 1 | Diagnostic |
| Sensor: IP address | 1 | Diagnostic. Disabled by default. |

Also: device triggers "Button 1 pressed once / twice / three times" and "Button 1 held", and the `logixdiy_button_action` bus event.

The button can be detached on the device's settings page. Then single, double and triple presses only fire events, for automations, and a hold still switches all outlets.

### Known limitations

- One meter measures the whole strip, so there is no per-outlet power.
- The energy readings are only as accurate as the device's calibration. Calibrate it on the device's own settings page.
- A single press takes effect about 0.4 s after the press, while the device waits to see whether another press follows.
- The outlets switch off for about 10 s while the device installs a firmware update.

## Logix Energy Plug

Replacement firmware for the AWP04L plug-in smart plug (ESP8266EX, 1 MB). It has one switched outlet, one button, a power LED, a WiFi LED and a BL0937 energy meter.

- **Firmware:** [logix-energy-plug-firmware](https://github.com/logichousepcb/logix-energy-plug-firmware), version 1.0.0 or later. On Tasmota 7.2.0, run `SetOption78 1` first (it turns off Tasmota's "Not compatible" check), then install it over Tasmota's web OTA form with the plain `firmware.bin`: that Tasmota can't take the gzipped image.

### Discovery

| Method | Requirement |
|---|---|
| mDNS (`_logix._tcp`) | Device and Home Assistant on the same network segment |
| MQTT (`logix/discovery/<id>`) | MQTT enabled on the device, using the same broker as Home Assistant's MQTT integration |
| Manual | Device IP address or hostname, e.g. `pow1725.local` |

### Entities

| Entity | Count | Notes |
|---|---|---|
| Switch (named after the device) | 1 | The outlet. Device class `outlet`. |
| Sensor: Voltage, Current, Power | 3 | Energy meter |
| Sensor: Apparent power, Reactive power, Power factor | 3 | Disabled by default |
| Sensor: Energy today, Energy yesterday, Energy total | 3 | kWh. Energy total is `total_increasing`, for the Energy dashboard. |
| Event: Button 1 | 1 | Fires `single`, `double`, `triple` or `hold` |
| Button: Button 1 single / double / triple press, hold | 4 | Act like the physical button: a single press toggles the plug, the others are only reported. Disabled by default. |
| Button: Restart | 1 | |
| Sensor: Wi-Fi signal | 1 | Diagnostic |
| Sensor: IP address | 1 | Diagnostic. Disabled by default. |

Also: device triggers "Button 1 pressed once / twice / three times" and "Button 1 held", and the `logixdiy_button_action` bus event.

The button can be detached on the device's settings page. Then a single press only fires an event, for automations, and a hold toggles the plug.

### Known limitations

- The energy readings are only as accurate as the device's calibration. Calibrate it on the device's own settings page.
- Power and current read zero while the plug is off.
- A single press takes effect about 0.4 s after the press, while the device waits to see whether another press follows.
- The plug switches off for a few seconds while the device installs a firmware update.

## Logix S31 Plug

Replacement firmware for the Sonoff S31 plug-in smart plug (ESP8266EX). It has one switched outlet, one button, a red LED wired to the relay, a blue WiFi LED and a CSE7766 energy meter. The HTTP and MQTT API is the Logix Energy Plug's, with model `logixs31`.

- **Firmware:** logix-s31-firmware, version 1.0.0 or later. It installs over ESPHome's web OTA (`web_server` with OTA on) with `firmware.bin.gz`. ESPHome compiles its WiFi into the image, so after the install the plug starts its setup AP `Logix-S31-XXXX` (unless the firmware was built with `secrets.ini`), and WiFi is set at `http://192.168.4.1`.

### Discovery

| Method | Requirement |
|---|---|
| mDNS (`_logix._tcp`) | Device and Home Assistant on the same network segment |
| MQTT (`logix/discovery/<id>`) | MQTT enabled on the device, using the same broker as Home Assistant's MQTT integration |
| Manual | Device IP address or hostname, e.g. `logix-s31-plug-2af9.local` |

### Entities

The same as the [Logix Energy Plug](#logix-energy-plug): the outlet switch (device class `outlet`), Voltage, Current and Power, Apparent power, Reactive power and Power factor (disabled by default), Energy today, yesterday and total, the Button 1 event, the four simulated button presses (disabled by default), Restart, and the Wi-Fi signal and IP address diagnostics. The device triggers and the `logixdiy_button_action` bus event are the same too.

### Known limitations

- The readings use the CSE7766's factory calibration, which the chip sends with every reading. Fine-tune it on the device's own settings page.
- Power and current read zero while the plug is off. Below about 50 mA the chip gives no current reading, so the device reports power / voltage instead.
- A single press takes effect about 0.4 s after the press, while the device waits to see whether another press follows.
- Replacing ESPHome leaves its entities in Home Assistant unavailable. Remove the old ESPHome device.

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

## Logix RGB Plug

Replacement firmware for a plug-in smart plug with an RGB night light (ESP8266EX, 1 MB, Tasmota template "RGB Light"). It has one switched outlet, one RGB light and one button: a single press toggles the outlet, a double press toggles the light. It has no energy meter.

- **Firmware:** [logix-rgb-plug-firmware](https://github.com/logichousepcb/logix-rgb-plug-firmware), version 1.0.0 or later. Install it over Tasmota's web OTA form with the gzipped image.

### Discovery

| Method | Requirement |
|---|---|
| mDNS (`_logix._tcp`) | Device and Home Assistant on the same network segment |
| MQTT (`logix/discovery/<id>`) | MQTT enabled on the device, using the same broker as Home Assistant's MQTT integration |
| Manual | Device IP address or hostname, e.g. `xtool-m1.local` |

### Entities

| Entity | Count | Notes |
|---|---|---|
| Switch (named after the device) | 1 | The outlet. Device class `outlet`. |
| Light: Light | 1 | RGB, brightness, transitions, effects `pulse` and `fast_pulse` |
| Event: Button 1 | 1 | Fires `single` (outlet toggled) or `double` (light toggled) |
| Button: Button 1 single press, Button 1 double press | 2 | Act like the physical button. Disabled by default. |
| Button: Restart | 1 | |
| Sensor: Wi-Fi signal | 1 | Diagnostic |
| Sensor: IP address | 1 | Diagnostic. Disabled by default. |

Also: the device triggers "Button 1 pressed once" and "Button 1 pressed twice", and the `logixdiy_button_action` bus event.

### Known limitations

- No energy monitoring: the hardware has no meter.
- A single press takes effect about 0.4 s after the press, while the device waits to see whether a second press follows.
- The plug switches off for about 10 s while the device installs a firmware update.

## Logix GR

The Logix GR ("Logix garage relay"): a custom ESP8266 board (4 MB, Tasmota template "LoGiX_GR") with a relay that is pulsed like a garage door wall button, a push button with a WS2812 RGB LED, and a DS18B20 temperature sensor. The button is decoupled: it only reports its actions, so Home Assistant decides what it does.

- **Firmware:** [logix-gr-firmware](https://github.com/logichousepcb/logix-gr-firmware), version 1.0.0 or later. Install it over Tasmota's web OTA form with the gzipped image.

### Discovery

| Method | Requirement |
|---|---|
| mDNS (`_logix._tcp`) | Device and Home Assistant on the same network segment |
| MQTT (`logix/discovery/<id>`) | MQTT enabled on the device, using the same broker as Home Assistant's MQTT integration |
| Manual | Device IP address or hostname, e.g. `garage-opener.local` |

### Entities

| Entity | Count | Notes |
|---|---|---|
| Button: Trigger | 1 | Pulses the relay for the pulse time set on the device (2.4 s by default). Ignored while a pulse is running. |
| Sensor: Temperature | 1 | °C from the device, shown in your unit system. Unavailable while the sensor has no reading. |
| Light: Button light | 1 | RGB, brightness, transitions, effects `pulse` and `fast_pulse` |
| Event: Button 1 | 1 | Fires `single`, `double`, `triple` or `hold` (4 s) |
| Button: Button 1 single / double / triple press, hold | 4 | Report the action like the physical button; nothing switches on the device. Disabled by default. |
| Button: Restart | 1 | |
| Sensor: Wi-Fi signal | 1 | Diagnostic |
| Sensor: IP address | 1 | Diagnostic. Disabled by default. |

Also: device triggers for each button action, and the `logixdiy_button_action` bus event.

### Known limitations

- There is no door position sensor, so there is no cover entity: the integration can pulse the relay but can't tell whether the door is open or closed.
- A single press is reported about 0.4 s after the press, while the device waits to see whether another press follows.

## Logix RGB Switch

Replacement firmware for the KAUF SRF10 RGB wall switch (ESP8266EX, 1 MB). It has one relay, one button covering the whole face, and two RGB LEDs (behind the button and in its corner) that the firmware drives together as one light. A single press toggles the relay, a double press toggles the light. It has no energy meter. The HTTP API is the Logix RGB Plug's: the relay is outlet 1 with key `plug`.

- **Firmware:** [logix-rgb-switch-firmware](https://github.com/logichousepcb/logix-rgb-switch-firmware), version 1.0.0 or later. Install it over Tasmota's web OTA form with the gzipped image.

### Discovery

| Method | Requirement |
|---|---|
| mDNS (`_logix._tcp`) | Device and Home Assistant on the same network segment |
| MQTT (`logix/discovery/<id>`) | MQTT enabled on the device, using the same broker as Home Assistant's MQTT integration |
| Manual | Device IP address or hostname, e.g. `kauff2.local` |

### Entities

| Entity | Count | Notes |
|---|---|---|
| Switch (named after the device) | 1 | The relay. Device class `switch`. |
| Light: Button light | 1 | RGB, brightness, transitions, effects `pulse` and `fast_pulse` |
| Event: Button 1 | 1 | Fires `single` (relay toggled) or `double` (light toggled) |
| Button: Button 1 single press, Button 1 double press | 2 | Act like the physical button. Disabled by default. |
| Button: Restart | 1 | |
| Sensor: Wi-Fi signal | 1 | Diagnostic |
| Sensor: IP address | 1 | Diagnostic. Disabled by default. |

Also: the device triggers "Button 1 pressed once" and "Button 1 pressed twice", and the `logixdiy_button_action` bus event.

### Known limitations

- No energy monitoring: the hardware has no meter.
- A single press takes effect about 0.4 s after the press, while the device waits to see whether a second press follows.
- The two LEDs always show the same color; they can't be set separately.
- The relay switches off for about 10 s while the device installs a firmware update.

## Logix Temp

Replacement firmware for a Wemos D1 mini (ESP8266EX, 4 MB) with a DS18B20 temperature sensor on D3 (GPIO0). It only reports the temperature: no relay, no button. Up to 4 DS18B20s on the same bus are reported; one is the normal case.

- **Firmware:** [logix-temp-firmware](https://github.com/logichousepcb/logix-temp-firmware), version 1.0.0 or later. It replaces ESPHome; the garage unit's ESPHome 1.14.4 had no OTA or web server, so the first install was over USB.

### Discovery

| Method | Requirement |
|---|---|
| mDNS (`_logix._tcp`) | Device and Home Assistant on the same network segment |
| MQTT (`logix/discovery/<id>`) | MQTT enabled on the device, using the same broker as Home Assistant's MQTT integration |
| Manual | Device IP address or hostname, e.g. `garage-temperature.local` |

### Entities

| Entity | Count | Notes |
|---|---|---|
| Sensor (named after the device) | 1 | Probe 1 in °C from the device, shown in your unit system. Attributes `address`, `min_celsius`, `max_celsius`. Unavailable while the probe isn't answering (3 failed readings in a row on the device) or isn't found. |
| Sensor: Temperature N | 0-3 | Further probes on the bus, numbered in the device's search order (by ROM address) |
| Button: Read now | 1 | Starts a reading at once. Config category. |
| Button: Restart | 1 | |
| Sensor: Wi-Fi signal | 1 | Diagnostic |
| Sensor: IP address | 1 | Diagnostic. Disabled by default. |

No events or device triggers: the device has no buttons.

### Known limitations

- The device's °F/°C setting only changes its own web page. Home Assistant always reads °C and converts to your unit system.
- Without MQTT the default poll interval is 10 s (set under **Configure**). The device reads every 10 s by default (2-3600 s on its Settings page).
- Probes added to the bus after setup get entities only after the integration is reloaded. Probe 1's sensor always exists, even if no probe was found at setup.
- The device's min/max reset when it restarts.

## Logix 3-Way Switch

Replacement firmware for the Moes 3-way wall switch (ESP8266EX, 1 MB, Tasmota template "Moes 3-Way"). It has a traveler relay, a sense input that reads whether the light circuit has power, one button and one LED. A 3-way switch can't turn the light on or off by itself, only move its relay to the other traveler, so the light's state comes from the sense input, and on and off move the relay only when the light has to change. The HTTP API is the Logix Plug's: the light is outlet 1 with key `light`.

- **Firmware:** logix-3way-firmware, version 1.0.0 or later. Install it over Tasmota's web OTA form with the gzipped image.

### Discovery

| Method | Requirement |
|---|---|
| mDNS (`_logix._tcp`) | Device and Home Assistant on the same network segment |
| MQTT (`logix/discovery/<id>`) | MQTT enabled on the device, using the same broker as Home Assistant's MQTT integration |
| Manual | Device IP address or hostname, e.g. `laundry-light.local` |

### Entities

| Entity | Count | Notes |
|---|---|---|
| Switch (named after the device) | 1 | The light, as sensed. Device class `switch`. Set **Show as: Light** in its settings to use it as a light. |
| Event: Button 1 | 1 | Fires `single`, `double`, `triple` or `hold` |
| Button: Button 1 single / double / triple press, hold | 4 | Act like the physical button: a single press toggles the light, the others are only reported. Disabled by default. |
| Button: Restart | 1 | |
| Sensor: Wi-Fi signal | 1 | Diagnostic |
| Sensor: IP address | 1 | Diagnostic. Disabled by default. |

Also: device triggers "Button 1 pressed once / twice / three times" and "Button 1 held", and the `logixdiy_button_action` bus event.

The button can be detached on the device's settings page. Then a single press only fires an event, for automations, and a hold toggles the light.

### Known limitations

- No energy monitoring: the hardware has no meter.
- A change made at the other 3-way switch shows up through MQTT within about 0.1 s; without MQTT, at the next poll.
- With no power on the light circuit (a tripped breaker, say) the light reads off, and turning it on moves the relay without effect.
- A single press takes effect about 0.4 s after the press, while the device waits to see whether another press follows.

## Logix Fixture

Firmware for the LoGiX base fixture board: an ESP-12F (ESP8266, 4 MB) driving an addressable RGB LED strip or string (WS2812/SK6812 type, GPIO2 by default, up to 800 LEDs) through a level shifter, with an IR receiver for the 24-key remote. The whole strip is one light with animated effects. Its HTTP API is its own (`/api/state` rather than `/api/controller`), and it has no MQTT.

- **Firmware:** logix-fixture-firmware, version 1.2.0 or later. Updates go over its web page (Firmware tab) or `POST /api/update`.

### Discovery

| Method | Requirement |
|---|---|
| mDNS (`_logix._tcp`) | Device and Home Assistant on the same network segment |
| Manual | Device IP address or hostname, e.g. `molly-s-tree.local` |

### Entities

| Entity | Count | Notes |
|---|---|---|
| Light (named after the device) | 1 | Brightness, RGB color and effects. The effect list comes from the device's `GET /api/effects`; "Solid" is Home Assistant's no-effect (`off`). Breathe, Color wipe, Theater chase, Twinkle, Comet and Candle use the color; the rainbows and Christmas ignore it. |
| Number: Effect speed | 1 | 0-100 %, the device's 0-255 speed. Changing it doesn't turn the light on. |
| Button: Identify | 1 | Blinks the LEDs white for about 3 s, even while off. Config category. |
| Button: Restart | 1 | |
| Sensor: Wi-Fi signal | 1 | Diagnostic |
| Sensor: IP address | 1 | Diagnostic. Disabled by default. |

No events or device triggers: the device has no buttons.

### Authentication

The device's API token is off by default. When it is on (Device tab of its web page), setup asks for a password: enter the token. The integration sends it as `X-Api-Key`.

### Known limitations

- No MQTT push, so changes from the IR remote or the web page show up at the next poll (5 s by default; set under **Configure**). The device's WebSocket push on port 81 isn't used yet.
- The device always fades brightness changes over 0.4 s itself, so `transition` isn't supported.
- The current limiter on the device may dim the strip below the brightness Home Assistant shows.
- Effects added by a later firmware appear after the integration is reloaded.

## Adding a device

When a new Logix device is ready:

1. Its firmware uses `BaseCore`, so it advertises `_logix._tcp`, serves `GET /api/info` and publishes `logix/discovery/<id>`.
2. Register its model ID in [`custom_components/logixdiy/models.py`](custom_components/logixdiy/models.py), with its display name, entity platforms and the class that parses its `/api/controller` state.
3. If its controls differ from the Logix 3's (buttons and RGB LEDs), add a state class in `api.py` and the platform code for them, as the Logix Vent does with `VentState`, `cover.py` and its status light.
4. Add tests with sample `/api/info` and state responses from the real firmware.
5. Add a row to the table above and a section for the device, then bump `version` in [`manifest.json`](custom_components/logixdiy/manifest.json).
