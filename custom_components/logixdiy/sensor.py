"""Diagnostic sensors from /api/status."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import SIGNAL_STRENGTH_DECIBELS_MILLIWATT, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import LogixConfigEntry, LogixCoordinator
from .entity import LogixEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class LogixSensorDescription(SensorEntityDescription):
    """Describes a status sensor."""

    value_fn: Callable[[dict[str, Any]], Any]


SENSORS: tuple[LogixSensorDescription, ...] = (
    LogixSensorDescription(
        key="wifi_signal",
        translation_key="wifi_signal",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda status: status.get("rssi") or None,
    ),
    LogixSensorDescription(
        key="ip_address",
        translation_key="ip_address",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda status: status.get("ip") or None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LogixConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up status sensors."""
    coordinator = entry.runtime_data
    async_add_entities(LogixStatusSensor(coordinator, description) for description in SENSORS)


class LogixStatusSensor(LogixEntity, SensorEntity):
    """A value from the device's status, refreshed every minute."""

    entity_description: LogixSensorDescription

    def __init__(self, coordinator: LogixCoordinator, description: LogixSensorDescription) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        """Current value."""
        if self.coordinator.status is None:
            return None
        return self.entity_description.value_fn(self.coordinator.status)
