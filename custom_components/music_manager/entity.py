"""Base entity: everything hangs off one "Music Manager" service device."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MusicManagerCoordinator


class MusicManagerEntity(CoordinatorEntity[MusicManagerCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: MusicManagerCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="Music Manager",
            manufacturer="HA Music Manager",
            model="Soulseek client (slskd)",
            sw_version=coordinator.data["status"]["version"],
            entry_type=DeviceEntryType.SERVICE,
        )
