"""Sensors: diagnostics from /api/status, and the Logix Outlet's energy meter."""

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
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfApparentPower,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfReactivePower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import EnergyReading, OutletState
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


@dataclass(frozen=True, kw_only=True)
class LogixEnergySensorDescription(SensorEntityDescription):
    """Describes an energy meter reading."""

    value_fn: Callable[[EnergyReading], float]


# Voltage, current and the powers are named after their device class; the counters need names.
ENERGY_SENSORS: tuple[LogixEnergySensorDescription, ...] = (
    LogixEnergySensorDescription(
        key="voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda e: e.voltage,
    ),
    LogixEnergySensorDescription(
        key="current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        value_fn=lambda e: e.current,
    ),
    LogixEnergySensorDescription(
        key="power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda e: e.power,
    ),
    LogixEnergySensorDescription(
        key="apparent_power",
        device_class=SensorDeviceClass.APPARENT_POWER,
        native_unit_of_measurement=UnitOfApparentPower.VOLT_AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        value_fn=lambda e: e.apparent_power,
    ),
    LogixEnergySensorDescription(
        key="reactive_power",
        device_class=SensorDeviceClass.REACTIVE_POWER,
        native_unit_of_measurement=UnitOfReactivePower.VOLT_AMPERE_REACTIVE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        value_fn=lambda e: e.reactive_power,
    ),
    LogixEnergySensorDescription(
        key="power_factor",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
        value_fn=lambda e: e.factor,
    ),
    LogixEnergySensorDescription(
        key="energy_today",
        translation_key="energy_today",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
        value_fn=lambda e: e.today,
    ),
    LogixEnergySensorDescription(
        key="energy_yesterday",
        translation_key="energy_yesterday",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=3,
        value_fn=lambda e: e.yesterday,
    ),
    # The one to use in the Energy dashboard.
    LogixEnergySensorDescription(
        key="energy_total",
        translation_key="energy_total",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
        value_fn=lambda e: e.total,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LogixConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up status sensors, and energy sensors on devices with a meter."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [LogixStatusSensor(coordinator, description) for description in SENSORS]
    if coordinator.capabilities.get("energy"):
        entities.extend(LogixEnergySensor(coordinator, description) for description in ENERGY_SENSORS)
    async_add_entities(entities)


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


class LogixEnergySensor(LogixEntity, SensorEntity):
    """A reading from the device's energy meter, which measures all outlets together."""

    entity_description: LogixEnergySensorDescription

    def __init__(self, coordinator: LogixCoordinator, description: LogixEnergySensorDescription) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def _energy(self) -> EnergyReading:
        state: OutletState = self.coordinator.data  # type: ignore[assignment]
        return state.energy  # type: ignore[return-value]  # only set up on devices with a meter

    @property
    def native_value(self) -> float:
        """Current value."""
        return self.entity_description.value_fn(self._energy)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """When the total started counting (energy total only)."""
        if self.entity_description.key != "energy_total":
            return None
        return {"total_start_time": self._energy.total_start_time}
