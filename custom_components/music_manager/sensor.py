"""Download activity sensors."""

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
from homeassistant.const import UnitOfDataRate
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MusicManagerConfigEntry, MusicManagerCoordinator
from .entity import MusicManagerEntity

PARALLEL_UPDATES = 0  # the coordinator does all the polling


@dataclass(frozen=True, kw_only=True)
class MusicManagerSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], float | int]


def _stat(name: str) -> Callable[[dict[str, Any]], float | int]:
    return lambda data: data["stats"][name]


SENSORS: tuple[MusicManagerSensorDescription, ...] = (
    MusicManagerSensorDescription(
        key="active_albums",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_stat("active_albums"),
    ),
    MusicManagerSensorDescription(
        key="queued_files",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_stat("queued_files"),
    ),
    MusicManagerSensorDescription(
        key="downloading_files",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_stat("downloading_files"),
    ),
    MusicManagerSensorDescription(
        key="download_speed",
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfDataRate.BYTES_PER_SECOND,
        suggested_unit_of_measurement=UnitOfDataRate.MEGABYTES_PER_SECOND,
        suggested_display_precision=1,
        value_fn=_stat("speed"),
    ),
    MusicManagerSensorDescription(
        key="completed_albums",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_stat("completed_albums"),
    ),
    MusicManagerSensorDescription(
        key="failed_albums",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_stat("failed_albums"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MusicManagerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        MusicManagerSensor(entry.runtime_data, description) for description in SENSORS
    )


class MusicManagerSensor(MusicManagerEntity, SensorEntity):
    entity_description: MusicManagerSensorDescription

    def __init__(
        self, coordinator: MusicManagerCoordinator, description: MusicManagerSensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | int:
        return self.entity_description.value_fn(self.coordinator.data)
