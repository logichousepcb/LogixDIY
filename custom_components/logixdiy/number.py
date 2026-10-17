"""Number entity: LED brightness for the whole device."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import LogixConfigEntry, LogixCoordinator
from .entity import LogixEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LogixConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the brightness number."""
    coordinator = entry.runtime_data
    if coordinator.capabilities.get("brightness"):
        async_add_entities([LogixBrightness(coordinator)])


class LogixBrightness(LogixEntity, NumberEntity):
    """Brightness of all LEDs, as a percentage of the device's 0-255 range."""

    _attr_translation_key = "brightness"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: LogixCoordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, "brightness")

    @property
    def native_value(self) -> int:
        """Brightness in percent."""
        return round(self.coordinator.data.brightness * 100 / 255)

    async def async_set_native_value(self, value: float) -> None:
        """Set brightness; the device debounces the flash write for slider drags."""
        await self.coordinator.async_command(self.coordinator.client.set_brightness(round(value * 255 / 100)))
