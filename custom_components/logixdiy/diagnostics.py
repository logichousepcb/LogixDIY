"""Diagnostics for LogixDIY."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant

from .coordinator import LogixConfigEntry

TO_REDACT = {CONF_PASSWORD, "savedSsid", "mac"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: LogixConfigEntry) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data({"data": dict(entry.data), "options": dict(entry.options)}, TO_REDACT),
        "info": async_redact_data(coordinator.info, TO_REDACT),
        "status": async_redact_data(coordinator.status or {}, TO_REDACT),
        "transport": {
            "mqtt_topic": coordinator.mqtt_topic,
            "push_active": coordinator.push_active,
            "update_interval": str(coordinator.update_interval),
        },
        "state": asdict(coordinator.data) if coordinator.data else None,
    }
