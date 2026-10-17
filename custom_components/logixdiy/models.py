"""Logix device models supported by this integration.

To add a device, register it in MODELS with the platforms it needs. Entities are built from
the "capabilities" block of the device's /api/info, so a model with buttons and RGB LEDs like
the Logix 3 needs nothing else. A device that works differently gets its own platform code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.const import Platform

from .const import SUPPORTED_API_VERSION


@dataclass(frozen=True, slots=True)
class LogixModel:
    """A supported model."""

    model: str
    name: str
    platforms: tuple[Platform, ...]


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
    """Default name for a device, e.g. "Logix 3 E527"."""
    name = info.get("name") or MODELS[info["model"]].name
    return f"{name} {str(info['id'])[-4:].upper()}"
