"""Select entities: the state of each LED (off, single, double, triple, hold)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
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
    """Set up LED state selects."""
    coordinator = entry.runtime_data
    async_add_entities(
        LogixLedStateSelect(coordinator, led) for led in range(1, coordinator.capabilities.get("leds", 0) + 1)
    )


class LogixLedStateSelect(LogixEntity, SelectEntity):
    """Which saved color an LED shows. Setting it never toggles, unlike a button press."""

    _attr_translation_key = "led_state"

    def __init__(self, coordinator: LogixCoordinator, led: int) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, f"led_{led}_state")
        self._led = led
        self._attr_options = coordinator.led_states
        self._attr_translation_placeholders = {"led": str(led)}

    @property
    def current_option(self) -> str:
        """Current LED state."""
        return self.coordinator.data.leds[self._led - 1].state

    async def async_select_option(self, option: str) -> None:
        """Change the LED state."""
        await self.coordinator.async_command(
            self.coordinator.client.set_controller({f"led{self._led}State": option})
        )
