"""Device triggers: "Button N pressed once / twice / three times / held"."""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.components.homeassistant.triggers import event as event_trigger
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    ATTR_DEVICE_ID,
    CONF_DEVICE_ID,
    CONF_DOMAIN,
    CONF_PLATFORM,
    CONF_TYPE,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.helpers.typing import ConfigType
import voluptuous as vol

from .const import ATTR_ACTION, ATTR_BUTTON, DOMAIN, EVENT_BUTTON_ACTION

CONF_SUBTYPE = "subtype"

# Validation can run before the device is loaded, so accept every action and button any
# model could have; async_get_triggers offers only the ones this device has.
TRIGGER_TYPES = ("single", "double", "triple", "hold")
MAX_BUTTONS = 8

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): vol.In(TRIGGER_TYPES),
        vol.Required(CONF_SUBTYPE): vol.In([f"button_{n}" for n in range(1, MAX_BUTTONS + 1)]),
    }
)


async def async_get_triggers(hass: HomeAssistant, device_id: str) -> list[dict[str, Any]]:
    """List the triggers for a device."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is not ConfigEntryState.LOADED or entry.runtime_data.device_id != device_id:
            continue
        coordinator = entry.runtime_data
        return [
            {
                CONF_PLATFORM: "device",
                CONF_DOMAIN: DOMAIN,
                CONF_DEVICE_ID: device_id,
                CONF_TYPE: action,
                CONF_SUBTYPE: f"button_{button}",
            }
            for button in range(1, coordinator.capabilities.get("buttons", 0) + 1)
            for action in coordinator.actions
            if action in TRIGGER_TYPES
        ]
    return []


async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Listen for the button action event."""
    event_config = event_trigger.TRIGGER_SCHEMA(
        {
            event_trigger.CONF_PLATFORM: "event",
            event_trigger.CONF_EVENT_TYPE: EVENT_BUTTON_ACTION,
            event_trigger.CONF_EVENT_DATA: {
                ATTR_DEVICE_ID: config[CONF_DEVICE_ID],
                ATTR_BUTTON: int(config[CONF_SUBTYPE].removeprefix("button_")),
                ATTR_ACTION: config[CONF_TYPE],
            },
        }
    )
    return await event_trigger.async_attach_trigger(
        hass, event_config, action, trigger_info, platform_type="device"
    )
