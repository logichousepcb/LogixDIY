"""Button entities: simulate a button action, and restart the device."""

from __future__ import annotations

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.const import EntityCategory
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
    """Set up buttons."""
    coordinator = entry.runtime_data
    entities: list[ButtonEntity] = [
        LogixPressButton(coordinator, button, action)
        for button in range(1, coordinator.capabilities.get("buttons", 0) + 1)
        for action in coordinator.actions
    ]
    entities.append(LogixRestartButton(coordinator))
    async_add_entities(entities)


class LogixPressButton(LogixEntity, ButtonEntity):
    """Acts exactly like the physical button: the LED toggles and an event fires."""

    # Twelve of these on a Logix 3; enable the ones you need.
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: LogixCoordinator, button: int, action: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, f"button_{button}_{action}")
        self._button = button
        self._action = action
        self._attr_translation_key = f"press_{action}"
        self._attr_translation_placeholders = {"button": str(button)}

    async def async_press(self) -> None:
        """Simulate the action."""
        await self.coordinator.async_command(self.coordinator.client.press(self._button, self._action))


class LogixRestartButton(LogixEntity, ButtonEntity):
    """Restart the device."""

    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: LogixCoordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, "restart")

    async def async_press(self) -> None:
        """Restart the device."""
        await self.coordinator.async_command(self.coordinator.client.reboot())
