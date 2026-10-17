"""Light entities: one per RGB LED.

The LED is "on" in any state other than off. Its effect is the state it shows (single, double,
triple or hold), and its color is the color saved for that state, so changing the color edits
that slot. Brightness is shared by all LEDs on the device.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_EFFECT,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
import voluptuous as vol

from .api import rgb_to_hex
from .const import DOMAIN, SERVICE_SET_LED_COLORS
from .coordinator import LogixConfigEntry, LogixCoordinator
from .entity import LogixEntity

PARALLEL_UPDATES = 1

RGB_SCHEMA = vol.All(vol.ExactSequence((cv.byte, cv.byte, cv.byte)), vol.Coerce(tuple))
ATTR_OFF_COLOR = "off_color"


def _color_attr(action: str) -> str:
    return f"{action}_color"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LogixConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up LED lights."""
    coordinator = entry.runtime_data
    async_add_entities(
        LogixLed(coordinator, led) for led in range(1, coordinator.capabilities.get("leds", 0) + 1)
    )

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_SET_LED_COLORS,
        {
            vol.Optional(_color_attr(action)): RGB_SCHEMA
            for action in ("single", "double", "triple", "hold", "off")
        },
        "async_set_led_colors",
    )


class LogixLed(LogixEntity, LightEntity):
    """One RGB LED."""

    _attr_color_mode = ColorMode.RGB
    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_supported_features = LightEntityFeature.EFFECT
    _attr_translation_key = "led"

    def __init__(self, coordinator: LogixCoordinator, led: int) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, f"led_{led}")
        self._led = led
        self._attr_effect_list = coordinator.actions
        self._attr_translation_placeholders = {"led": str(led)}

    @property
    def _state(self) -> str:
        return self.coordinator.data.leds[self._led - 1].state

    @property
    def is_on(self) -> bool:
        """LED is showing one of its action colors."""
        return self._state != "off"

    @property
    def effect(self) -> str | None:
        """The action color being shown."""
        return self._state if self.is_on else None

    @property
    def rgb_color(self) -> tuple[int, int, int]:
        """The color for the current state (the single press color while off)."""
        state = self._state if self.is_on else self.coordinator.actions[0]
        return self.coordinator.color_for(self._led, state)

    @property
    def brightness(self) -> int:
        """Device-wide brightness."""
        return self.coordinator.data.brightness

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Show an action color, optionally changing that color and the brightness."""
        state = kwargs.get(ATTR_EFFECT) or (self._state if self.is_on else self.coordinator.actions[0])
        if state not in self.coordinator.actions:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_effect",
                translation_placeholders={"effect": str(state)},
            )

        fields: dict[str, Any] = {f"led{self._led}State": state}
        if ATTR_RGB_COLOR in kwargs:
            slot = self.coordinator.actions.index(state) + 1
            fields[f"led{self._led}Color{slot}"] = rgb_to_hex(kwargs[ATTR_RGB_COLOR])
        if ATTR_BRIGHTNESS in kwargs:
            fields["brightness"] = kwargs[ATTR_BRIGHTNESS]
        await self.coordinator.async_command(self.coordinator.client.set_controller(fields))

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Show the off color."""
        await self.coordinator.async_command(
            self.coordinator.client.set_controller({f"led{self._led}State": "off"})
        )

    async def async_set_led_colors(self, **colors: tuple[int, int, int]) -> None:
        """Set any of this LED's saved colors without changing what it shows."""
        if not colors:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="no_colors")
        fields: dict[str, str] = {}
        for slot, action in enumerate(self.coordinator.actions, start=1):
            if (rgb := colors.get(_color_attr(action))) is not None:
                fields[f"led{self._led}Color{slot}"] = rgb_to_hex(rgb)
        if (rgb := colors.get(ATTR_OFF_COLOR)) is not None:
            fields[f"led{self._led}OffColor"] = rgb_to_hex(rgb)
        await self.coordinator.async_command(self.coordinator.client.set_controller(fields))
