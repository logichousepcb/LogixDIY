"""Cover entity: the Logix Vent's motorised vent.

The vent has no position sensor. The device reports the state it was last driven to, plus
whether the motor is running and for how much longer.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.cover import CoverDeviceClass, CoverEntity, CoverEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import VentState
from .coordinator import LogixConfigEntry, LogixCoordinator
from .entity import LogixEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LogixConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the vent."""
    coordinator = entry.runtime_data
    if "vent" in coordinator.capabilities:
        async_add_entities([LogixVent(coordinator)])


class LogixVent(LogixEntity, CoverEntity):
    """A vent driven open or closed for a fixed run time."""

    _attr_device_class = CoverDeviceClass.DAMPER
    _attr_translation_key = "vent"
    _attr_name = None

    def __init__(self, coordinator: LogixCoordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, "vent")
        features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE
        if coordinator.capabilities["vent"].get("supportsStop"):
            features |= CoverEntityFeature.STOP
        self._attr_supported_features = features

    @property
    def _vent(self) -> VentState:
        return self.coordinator.data  # type: ignore[return-value]

    @property
    def is_closed(self) -> bool:
        """The vent was last driven closed."""
        return self._vent.vent_state == "closed"

    @property
    def is_opening(self) -> bool:
        """The motor is opening the vent."""
        return self._vent.operation == "opening"

    @property
    def is_closing(self) -> bool:
        """The motor is closing the vent."""
        return self._vent.operation == "closing"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """How long the motor keeps running."""
        return {"remaining_ms": self._vent.remaining_ms}

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the vent."""
        await self.coordinator.async_command(self.coordinator.client.set_vent("open"))

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the vent."""
        await self.coordinator.async_command(self.coordinator.client.set_vent("close"))

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the motor."""
        await self.coordinator.async_command(self.coordinator.client.set_vent("stop"))
