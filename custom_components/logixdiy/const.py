"""Constants for the LogixDIY integration."""

from __future__ import annotations

from datetime import timedelta
import logging

DOMAIN = "logixdiy"
LOGGER = logging.getLogger(__package__)

MANUFACTURER = "Logix"

# Every Logix device serves /api/info and advertises this mDNS service.
ZEROCONF_TYPE = "_logix._tcp.local."
MQTT_DISCOVERY_PREFIX = "logix/discovery"

# Highest /api/info "api" contract version this integration understands.
SUPPORTED_API_VERSION = 1

CONF_USE_MQTT = "use_mqtt"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_USE_MQTT = True
# Seconds between polls when there is no MQTT push; button events are detected from these polls.
DEFAULT_SCAN_INTERVAL = 1.0
# While MQTT pushes state, polling only resyncs and refreshes diagnostics.
PUSH_SCAN_INTERVAL = timedelta(seconds=60)
STATUS_INTERVAL = 60.0

# Fired on the event bus for every completed button action; device triggers listen for it.
EVENT_BUTTON_ACTION = f"{DOMAIN}_button_action"
ATTR_BUTTON = "button"
ATTR_ACTION = "action"

SERVICE_SET_LED_COLORS = "set_led_colors"
