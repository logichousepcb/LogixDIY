"""Switch entities: the Logix Outlet's outlets, named after their position (Top, Bottom), and
the single outlet of the Logix Plug, Logix RGB Plug and Logix RGB Switch (its relay), which takes
the device's own name."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import OutletState
from .coordinator import LogixConfigEntry, LogixCoordinator
from .entity import LogixEntity

PARALLEL_UPDATES = 1

# Outlet keys from /api/info that have their own translated name; others are "Outlet N".
NAMED_OUTLETS = ("top", "bottom")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LogixConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one switch per outlet."""
    coordinator = entry.runtime_data
    keys = coordinator.capabilities.get("outletKeys", [])
    async_add_entities(
        LogixOutlet(coordinator, outlet, keys[outlet - 1] if outlet <= len(keys) else None)
        for outlet in range(1, coordinator.capabilities.get("outlets", 0) + 1)
    )


class LogixOutlet(LogixEntity, SwitchEntity):
    """One outlet. The physical button for it toggles it too, with or without Home Assistant."""

    def __init__(self, coordinator: LogixCoordinator, outlet: int, key: str | None) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, f"outlet_{outlet}")
        self._attr_device_class: SwitchDeviceClass = coordinator.model.outlet_device_class
        self._outlet = outlet
        if coordinator.capabilities.get("outlets") == 1:
            self._attr_name = None  # the device's only outlet: "Entry Table Lamp", not "... Outlet 1"
        elif key in NAMED_OUTLETS:
            self._attr_translation_key = f"outlet_{key}"
        else:
            self._attr_translation_key = "outlet"
            self._attr_translation_placeholders = {"outlet": str(outlet)}

    @property
    def _state(self) -> OutletState:
        return self.coordinator.data  # type: ignore[return-value]

    @property
    def is_on(self) -> bool:
        """The outlet is switched on."""
        return self._state.outlets[self._outlet - 1]

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Switch the outlet on."""
        await self.coordinator.async_command(self.coordinator.client.set_outlet(self._outlet, "on"))

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Switch the outlet off."""
        await self.coordinator.async_command(self.coordinator.client.set_outlet(self._outlet, "off"))

    async def async_toggle(self, **kwargs: Any) -> None:
        """Toggle on the device, so it can't race a button press."""
        await self.coordinator.async_command(self.coordinator.client.set_outlet(self._outlet, "toggle"))
