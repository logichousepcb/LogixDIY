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

from homeassistant.const import Platform

from .api import ControllerState, LogixState, OutletState, VentState
from .const import SUPPORTED_API_VERSION


@dataclass(frozen=True, slots=True)
class LogixModel:
    """A supported model."""

    model: str
    name: str
    platforms: tuple[Platform, ...]
    parse_state: Callable[[dict[str, Any]], LogixState]


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
