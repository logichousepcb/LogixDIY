"""Data coordinator for Logix devices: HTTP polling with optional MQTT push."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from datetime import timedelta
import json
import time
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    RGB,
    ControllerState,
    LogixAuthError,
    LogixClient,
    LogixCommandError,
    LogixConnectionError,
    LogixError,
)
from .const import (
    ATTR_ACTION,
    ATTR_BUTTON,
    CONF_SCAN_INTERVAL,
    CONF_USE_MQTT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_USE_MQTT,
    DOMAIN,
    EVENT_BUTTON_ACTION,
    LOGGER,
    PUSH_SCAN_INTERVAL,
    STATUS_INTERVAL,
)
from .models import MODELS, LogixModel

if TYPE_CHECKING:
    from homeassistant.components.mqtt import ReceiveMessage

type LogixConfigEntry = ConfigEntry[LogixCoordinator]

type ActionListener = Callable[[int, str], None]


class LogixCoordinator(DataUpdateCoordinator[ControllerState]):
    """Keeps one device's state current and turns its button actions into events."""

    config_entry: LogixConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: LogixConfigEntry, client: LogixClient, info: dict[str, Any]
    ) -> None:
        """Initialize the coordinator."""
        self._poll_interval = timedelta(seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {info['id']}",
            update_interval=self._poll_interval,
            always_update=False,
        )
        self.client = client
        self.info = info
        self.model: LogixModel = MODELS[info["model"]]
        self.device_id: str | None = None
        self.status: dict[str, Any] | None = None
        self.push_active = False
        self.mqtt_topic: str | None = None
        self._status_at = 0.0
        self._action_counts: tuple[int, ...] | None = None
        self._action_listeners: list[ActionListener] = []

    # Capabilities ------------------------------------------------------------------------------

    @property
    def device_uid(self) -> str:
        """Stable device ID (the MAC address without separators)."""
        return self.info["id"]

    @property
    def capabilities(self) -> dict[str, Any]:
        """The "capabilities" block of /api/info."""
        return self.info.get("capabilities", {})

    @property
    def actions(self) -> list[str]:
        """Button actions, e.g. single, double, triple, hold. Also the LED color slots."""
        return list(self.capabilities.get("actions", ()))

    @property
    def led_states(self) -> list[str]:
        """LED states: "off" followed by the actions."""
        return list(self.capabilities.get("ledStates", ()))

    def color_for(self, led: int, state: str) -> RGB:
        """Color LED `led` (1-based) shows in `state`."""
        led_state = self.data.leds[led - 1]
        if state not in self.actions:
            return led_state.off_color
        return led_state.colors[self.actions.index(state)]

    # Polling -----------------------------------------------------------------------------------

    async def _async_update_data(self) -> ControllerState:
        try:
            data = await self.client.get_controller()
            if self.status is None or time.monotonic() - self._status_at >= STATUS_INTERVAL:
                await self._async_update_status()
        except LogixAuthError as err:
            raise ConfigEntryAuthFailed(translation_domain=DOMAIN, translation_key="invalid_auth") from err
        except LogixError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err)},
            ) from err

        # While MQTT is pushing, actions arrive on their own topic; polls only move the baseline.
        self._track_actions(data, fire=not self.push_active)
        return data

    async def _async_update_status(self) -> None:
        try:
            self.status = await self.client.get_status()
        except LogixConnectionError as err:
            LOGGER.debug("Could not read status of %s: %s", self.client.host, err)
            return
        self._status_at = time.monotonic()

        firmware = self.status.get("version")
        if firmware and firmware != self.info.get("fw"):
            self.info = {**self.info, "fw": firmware}
            if self.device_id:
                dr.async_get(self.hass).async_update_device(self.device_id, sw_version=firmware)

    # Button actions ----------------------------------------------------------------------------

    @callback
    def async_add_action_listener(self, listener: ActionListener) -> CALLBACK_TYPE:
        """Call `listener(button, action)` for every completed button action."""
        self._action_listeners.append(listener)
        return lambda: self._action_listeners.remove(listener)

    @callback
    def _track_actions(self, data: ControllerState, *, fire: bool) -> None:
        """Compare actionCount with the previous state and fire events for new actions."""
        counts = tuple(b.action_count for b in data.buttons)
        previous, self._action_counts = self._action_counts, counts
        if not fire or previous is None or len(previous) != len(counts):
            return
        for index, (old, new) in enumerate(zip(previous, counts, strict=True)):
            if new < old:
                old = 0  # the device restarted and its counters reset
            # Several actions between two polls collapse into the most recent one.
            if new > old and (action := data.buttons[index].last_action):
                self._fire_action(index + 1, action)

    @callback
    def _fire_action(self, button: int, action: str) -> None:
        LOGGER.debug("%s button %s: %s", self.device_uid, button, action)
        for listener in list(self._action_listeners):
            listener(button, action)
        self.hass.bus.async_fire(
            EVENT_BUTTON_ACTION,
            {ATTR_DEVICE_ID: self.device_id, ATTR_BUTTON: button, ATTR_ACTION: action},
        )

    # MQTT push ---------------------------------------------------------------------------------

    async def async_setup_push(self) -> None:
        """Subscribe to the device's MQTT topics if HA's MQTT integration can see them."""
        mqtt_info = self.info.get("mqtt") or {}
        topic = mqtt_info.get("topic")
        if (
            not self.config_entry.options.get(CONF_USE_MQTT, DEFAULT_USE_MQTT)
            or not mqtt_info.get("enabled")
            or not topic
            or "mqtt" not in self.hass.config.components
        ):
            return

        # Imported here: the MQTT integration's requirements only exist when it is set up.
        from homeassistant.components import mqtt

        if not await mqtt.async_wait_for_mqtt_client(self.hass):
            return

        self.mqtt_topic = topic
        for suffix, handler in (
            ("status", self._handle_mqtt_status),
            ("state", self._handle_mqtt_state),
            ("button/+/action", self._handle_mqtt_action),
        ):
            self.config_entry.async_on_unload(
                await mqtt.async_subscribe(self.hass, f"{topic}/{suffix}", handler)
            )
        LOGGER.debug("Subscribed to %s/# for %s", topic, self.device_uid)

    @callback
    def _set_push_active(self, active: bool) -> None:
        if active == self.push_active:
            return
        self.push_active = active
        self.update_interval = PUSH_SCAN_INTERVAL if active else self._poll_interval
        LOGGER.debug("%s: MQTT push %s", self.device_uid, "active" if active else "inactive")
        if not active:
            # Reschedule now; the next poll may be up to PUSH_SCAN_INTERVAL away.
            self.config_entry.async_create_background_task(
                self.hass, self.async_refresh(), f"{DOMAIN} resume polling"
            )

    @callback
    def _handle_mqtt_status(self, msg: ReceiveMessage) -> None:
        self._set_push_active(msg.payload == "online")

    @callback
    def _handle_mqtt_state(self, msg: ReceiveMessage) -> None:
        try:
            data = ControllerState.from_json(json.loads(msg.payload))
        except (ValueError, TypeError, LogixConnectionError) as err:
            LOGGER.debug("Ignoring bad state on %s: %s", msg.topic, err)
            return
        self._set_push_active(True)
        self._track_actions(data, fire=False)
        self.async_set_updated_data(data)

    @callback
    def _handle_mqtt_action(self, msg: ReceiveMessage) -> None:
        # Topic: <base>/button/<n>/action
        try:
            button = int(msg.topic.rsplit("/", 2)[-2])
        except ValueError:
            return
        if msg.payload not in self.actions or not 1 <= button <= self.capabilities.get("buttons", 0):
            return
        self._set_push_active(True)
        self._fire_action(button, str(msg.payload))

    # Commands ----------------------------------------------------------------------------------

    async def async_command(self, command: Coroutine[Any, Any, None]) -> None:
        """Run a device command, translating errors, then bring the state up to date."""
        try:
            await command
        except LogixAuthError as err:
            self.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="invalid_auth") from err
        except LogixCommandError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_rejected",
                translation_placeholders={"error": str(err)},
            ) from err
        except LogixConnectionError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
                translation_placeholders={"error": str(err)},
            ) from err
        # With MQTT the device publishes its new state within 100 ms; otherwise fetch it.
        if not self.push_active:
            await self.async_refresh()
