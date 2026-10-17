"""Event entities: one per button, firing single, double, triple and hold."""

from __future__ import annotations

from homeassistant.components.event import EventDeviceClass, EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import LogixConfigEntry, LogixCoordinator
from .entity import LogixEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LogixConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up button event entities."""
    coordinator = entry.runtime_data
    async_add_entities(
        LogixButtonEvent(coordinator, button)
        for button in range(1, coordinator.capabilities.get("buttons", 0) + 1)
    )


class LogixButtonEvent(LogixEntity, EventEntity):
    """Fires when a button completes an action."""

    _attr_device_class = EventDeviceClass.BUTTON
    _attr_translation_key = "button"

    def __init__(self, coordinator: LogixCoordinator, button: int) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, f"button_{button}")
        self._button = button
        self._attr_event_types = coordinator.actions
        self._attr_translation_placeholders = {"button": str(button)}

    async def async_added_to_hass(self) -> None:
        """Listen for actions."""
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.async_add_action_listener(self._handle_action))

    @callback
    def _handle_action(self, button: int, action: str) -> None:
        if button == self._button:
            self._trigger_event(action)
            self.async_write_ha_state()
