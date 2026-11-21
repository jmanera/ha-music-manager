from __future__ import annotations

import copy
from collections.abc import Generator
from typing import Any

import pytest
from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.music_manager.const import DOMAIN

HOST = "abc123-music-manager"
BASE = f"http://{HOST}:8099/api"
ENTRY_DATA = {CONF_HOST: HOST, CONF_PORT: 8099, CONF_API_KEY: "secret-key"}

OVERVIEW: dict[str, Any] = {
    "status": {
        "version": "0.2.0",
        "engine": "managed",
        "connected": True,
        "logged_in": True,
        "server_state": "Connected, LoggedIn",
        "username": "juan",
    },
    "stats": {
        "active_albums": 1,
        "queued_files": 3,
        "downloading_files": 2,
        "completed_albums": 0,
        "failed_albums": 0,
        "speed": 2_500_000.0,
    },
    "downloads": [
        {
            "username": "alice",
            "directory": "Music\\OK Computer",
            "title": "OK Computer",
            "state": "downloading",
            "percent": 40.0,
            "file_count": 12,
        }
    ],
}

ALBUM = {
    "username": "alice",
    "directory": "Music\\OK Computer",
    "title": "OK Computer",
    "track_count": 12,
    "quality": "FLAC",
    "lossless": True,
    "total_size": 400_000_000,
    "total_length": 3200,
    "has_free_upload_slot": True,
    "queue_length": 0,
    "upload_speed": 3_000_000,
    "score": 96.5,
}


def overview(**changes: Any) -> dict[str, Any]:
    data = copy.deepcopy(OVERVIEW)
    for key, value in changes.items():
        data[key] = value
    return data


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> Generator[None]:
    yield


@pytest.fixture
def entry() -> MockConfigEntry:
    return MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data=ENTRY_DATA, title="Music Manager")


@pytest.fixture
async def loaded_entry(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> MockConfigEntry:
    aioclient_mock.get(f"{BASE}/overview", json=OVERVIEW)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry
