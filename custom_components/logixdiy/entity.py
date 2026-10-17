"""Base entity for Logix devices."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import LogixCoordinator


class LogixEntity(CoordinatorEntity[LogixCoordinator]):
    """An entity belonging to one Logix device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: LogixCoordinator, key: str) -> None:
        """Initialize the entity; `key` makes the unique ID unique within the device."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_uid}_{key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, coordinator.device_uid)})
