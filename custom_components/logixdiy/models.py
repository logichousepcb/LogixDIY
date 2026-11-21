"""Logix device models supported by this integration.

To add a device, register it in MODELS with the platforms it needs and the class that parses
its /api/controller state. Entities are built from the "capabilities" block of the device's
/api/info, so a model with buttons and RGB LEDs like the Logix 3 needs nothing else. A device
that works differently gets its own state class and platform code, like the Logix Vent.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchDeviceClass
from homeassistant.const import Platform

from .api import ControllerState, LogixState, OutletState, TempState, VentState
from .const import DEFAULT_SCAN_INTERVAL, SUPPORTED_API_VERSION


@dataclass(frozen=True, slots=True)
class LogixModel:
    """A supported model."""

    model: str
    name: str
    platforms: tuple[Platform, ...]
    parse_state: Callable[[dict[str, Any]], LogixState]
    # The relay of a wall switch is a switch, not an outlet.
    outlet_device_class: SwitchDeviceClass = SwitchDeviceClass.OUTLET
    # Name of the statusLight entity, if the capabilities alone don't tell (see light.py).
    light_translation_key: str | None = None
    # Poll interval without MQTT, unless the user sets one. Devices with buttons poll every
    # second to catch presses; a sensor that reads every 10 s needs far less.
    default_scan_interval: float = DEFAULT_SCAN_INTERVAL


MODELS: dict[str, LogixModel] = {
    model.model: model
    for model in (
        LogixModel(
            model="logix3",
            name="Logix 3",
            platforms=(
                Platform.BUTTON,
                Platform.EVENT,
                Platform.LIGHT,
                Platform.NUMBER,
                Platform.SELECT,
                Platform.SENSOR,
            ),
            parse_state=ControllerState.from_json,
        ),
        LogixModel(
            model="logixvent",
            name="Logix Vent",
            platforms=(
                Platform.BUTTON,
                Platform.COVER,
                Platform.EVENT,
                Platform.LIGHT,
                Platform.SENSOR,
            ),
            parse_state=VentState.from_json,
        ),
        LogixModel(
            model="logixoutlet",
            name="Logix Outlet",
            platforms=(
                Platform.BUTTON,
                Platform.EVENT,
                Platform.SENSOR,
                Platform.SWITCH,
            ),
            parse_state=OutletState.from_json,
        ),
        LogixModel(
            model="logixplug3",
            name="Logix Plug 3",
            platforms=(
                Platform.BUTTON,
                Platform.EVENT,
                Platform.SENSOR,
                Platform.SWITCH,
            ),
            parse_state=OutletState.from_json,
        ),
        LogixModel(
            model="logixenergyplug",
            name="Logix Energy Plug",
            platforms=(
                Platform.BUTTON,
                Platform.EVENT,
                Platform.SENSOR,
                Platform.SWITCH,
            ),
            parse_state=OutletState.from_json,
        ),
        LogixModel(
            # Sonoff S31: the Logix Energy Plug's API on a CSE7766 meter.
            model="logixs31",
            name="Logix S31 Plug",
            platforms=(
                Platform.BUTTON,
                Platform.EVENT,
                Platform.SENSOR,
                Platform.SWITCH,
            ),
            parse_state=OutletState.from_json,
        ),
        LogixModel(
            model="logixplug",
            name="Logix Plug",
            platforms=(
                Platform.BUTTON,
                Platform.EVENT,
                Platform.SENSOR,
                Platform.SWITCH,
            ),
            parse_state=OutletState.from_json,
        ),
        LogixModel(
            model="logixrgbplug",
            name="Logix RGB Plug",
            platforms=(
                Platform.BUTTON,
                Platform.EVENT,
                Platform.LIGHT,
                Platform.SENSOR,
                Platform.SWITCH,
            ),
            parse_state=OutletState.from_json,
        ),
        LogixModel(
            model="logixrgbswitch",
            name="Logix RGB Switch",
            platforms=(
                Platform.BUTTON,
                Platform.EVENT,
                Platform.LIGHT,
                Platform.SENSOR,
                Platform.SWITCH,
            ),
            parse_state=OutletState.from_json,
            outlet_device_class=SwitchDeviceClass.SWITCH,
            light_translation_key="button_light",  # the RGB light behind the button face
        ),
        LogixModel(
            # Moes 3-way wall switch. Its one outlet is the light: the state is what the device
            # senses on the light circuit, so it follows the other 3-way switch too, and the
            # device moves its traveler relay only when the light has to change.
            model="logix3way",
            name="Logix 3-Way Switch",
            platforms=(
                Platform.BUTTON,
                Platform.EVENT,
                Platform.SENSOR,
                Platform.SWITCH,
            ),
            parse_state=OutletState.from_json,
            outlet_device_class=SwitchDeviceClass.SWITCH,
        ),
        LogixModel(
            model="logixgr",
            name="Logix GR",
            platforms=(
                Platform.BUTTON,
                Platform.EVENT,
                Platform.LIGHT,
                Platform.SENSOR,
            ),
            parse_state=OutletState.from_json,
        ),
        LogixModel(
            model="logixtemp",
            name="Logix Temp",
            platforms=(
                Platform.BUTTON,
                Platform.SENSOR,
            ),
            parse_state=TempState.from_json,
            default_scan_interval=10.0,
        ),
    )
}


def unsupported_reason(info: dict[str, Any]) -> str | None:
    """Return a config flow abort reason if this device can't be set up, else None."""
    if info.get("model") not in MODELS:
        return "not_supported"
    if int(info.get("api", 0)) > SUPPORTED_API_VERSION:
        return "api_too_new"
    return None


def device_title(info: dict[str, Any]) -> str:
    """Default name for a device: "Logix 3 E527", or the name the user gave it ("Family Room Outlet")."""
    model_name = MODELS[info["model"]].name
    name = info.get("name") or model_name
    if name != model_name:
        return name
    return f"{name} {str(info['id'])[-4:].upper()}"
