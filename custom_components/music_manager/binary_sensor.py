"""Soulseek connection state."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.components.binary_sensor.const import BinarySensorDeviceClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MusicManagerConfigEntry, MusicManagerCoordinator
from .entity import MusicManagerEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MusicManagerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([MusicManagerConnected(entry.runtime_data)])


class MusicManagerConnected(MusicManagerEntity, BinarySensorEntity):
    """On when logged in to the Soulseek network (connected but not logged in counts as off)."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: MusicManagerCoordinator) -> None:
        super().__init__(coordinator, "connected")

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data["status"]["logged_in"])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        status = self.coordinator.data["status"]
        return {"server_state": status["server_state"], "username": status["username"]}
