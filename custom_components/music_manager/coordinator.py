"""Polls the app and turns finished downloads into Home Assistant events."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MusicManagerApi, MusicManagerAuthError, MusicManagerError
from .const import DOMAIN, EVENT_DOWNLOAD_COMPLETED, EVENT_DOWNLOAD_FAILED, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

type MusicManagerConfigEntry = ConfigEntry[MusicManagerCoordinator]


class MusicManagerCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    config_entry: MusicManagerConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: MusicManagerConfigEntry, api: MusicManagerApi
    ) -> None:
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=SCAN_INTERVAL
        )
        self.api = api
        # Album folder -> last seen state. None until the first poll, so downloads that
        # finished while Home Assistant was down don't fire events on startup.
        self._states: dict[tuple[str, str], str] | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            data = await self.api.overview()
        except MusicManagerAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except MusicManagerError as err:
            raise UpdateFailed(f"Error talking to the Music Manager app: {err}") from err
        self._fire_events(data["downloads"])
        return data

    def _fire_events(self, downloads: list[dict[str, Any]]) -> None:
        current = {(d["username"], d["directory"]): d for d in downloads}
        if self._states is not None:
            for key, download in current.items():
                state = download["state"]
                if state == self._states.get(key):
                    continue
                event = {
                    "completed": EVENT_DOWNLOAD_COMPLETED,
                    "failed": EVENT_DOWNLOAD_FAILED,
                }.get(state)
                if event:
                    self.hass.bus.async_fire(
                        event,
                        {
                            "title": download["title"],
                            "username": download["username"],
                            "directory": download["directory"],
                            "file_count": download["file_count"],
                        },
                    )
        self._states = {key: d["state"] for key, d in current.items()}
