from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.music_manager.const import (
    DOMAIN,
    EVENT_DOWNLOAD_COMPLETED,
    EVENT_DOWNLOAD_FAILED,
)

from .conftest import ALBUM, BASE, OVERVIEW, overview


async def test_entities(hass: HomeAssistant, loaded_entry: MockConfigEntry) -> None:
    assert loaded_entry.state is ConfigEntryState.LOADED

    speed = hass.states.get("sensor.music_manager_download_speed")
    assert speed is not None
    assert float(speed.state) == pytest.approx(2.5)  # 2.5 MB/s
    assert speed.attributes["unit_of_measurement"] == "MB/s"

    for entity_id, value in {
        "sensor.music_manager_active_albums": "1",
        "sensor.music_manager_queued_files": "3",
        "sensor.music_manager_downloading_files": "2",
        "sensor.music_manager_completed_albums": "0",
        "sensor.music_manager_failed_albums": "0",
    }.items():
        state = hass.states.get(entity_id)
        assert state is not None, entity_id
        assert state.state == value, entity_id

    connected = hass.states.get("binary_sensor.music_manager_soulseek_connection")
    assert connected is not None
    assert connected.state == "on"
    assert connected.attributes["username"] == "juan"
    assert connected.attributes["error"] is None

    assert await hass.config_entries.async_unload(loaded_entry.entry_id)
    assert loaded_entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_retries_when_app_is_down(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{BASE}/overview", status=503, json={"detail": "starting"})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_auth_failure_starts_reauth(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{BASE}/overview", status=403)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [f["context"]["source"] for f in flows] == ["reauth"]


async def _poll(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, data: object) -> None:
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{BASE}/overview", json=data)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=11))
    await hass.async_block_till_done()


async def test_download_events(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    events: list[Event] = []

    @callback
    def record(event: Event) -> None:
        events.append(event)

    hass.bus.async_listen(EVENT_DOWNLOAD_COMPLETED, record)
    hass.bus.async_listen(EVENT_DOWNLOAD_FAILED, record)

    done = dict(OVERVIEW["downloads"][0], state="completed", percent=100.0)
    failed = {
        "username": "bob",
        "directory": "X\\Broken",
        "title": "Broken",
        "state": "failed",
        "percent": 10.0,
        "file_count": 3,
    }
    await _poll(hass, aioclient_mock, overview(downloads=[done, failed]))
    assert [(e.event_type, e.data["title"]) for e in events] == [
        (EVENT_DOWNLOAD_COMPLETED, "OK Computer"),
        (EVENT_DOWNLOAD_FAILED, "Broken"),
    ]
    assert events[0].data == {
        "title": "OK Computer",
        "username": "alice",
        "directory": "Music\\OK Computer",
        "file_count": 12,
    }

    # Unchanged states don't fire again.
    await _poll(hass, aioclient_mock, overview(downloads=[done, failed]))
    assert len(events) == 2


async def test_no_events_for_downloads_finished_before_startup(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    events: list[Event] = []
    hass.bus.async_listen(EVENT_DOWNLOAD_COMPLETED, events.append)
    done = dict(OVERVIEW["downloads"][0], state="completed")
    aioclient_mock.get(f"{BASE}/overview", json=overview(downloads=[done]))
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert events == []


async def test_search_action(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    result = {"query": "ok computer", "response_count": 7, "albums": [ALBUM]}
    aioclient_mock.post(f"{BASE}/search-and-wait", json=result)
    response = await hass.services.async_call(
        DOMAIN,
        "search",
        {"query": "ok computer", "lossless_only": True, "limit": 3},
        blocking=True,
        return_response=True,
    )
    assert response == result
    sent = aioclient_mock.mock_calls[-1][2]
    assert sent == {
        "query": "ok computer",
        "timeout": 20.0,
        "lossless_only": True,
        "free_slot_only": False,
        "min_tracks": 1,
        "limit": 3,
    }


async def test_download_best_action(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(
        f"{BASE}/download-best", status=202, json={"query": "ok computer", "album": ALBUM}
    )
    response = await hass.services.async_call(
        DOMAIN,
        "download_best",
        {"query": "ok computer", "min_tracks": 8, "search_time": 30},
        blocking=True,
        return_response=True,
    )
    assert response is not None
    assert response["album"]["title"] == "OK Computer"
    assert aioclient_mock.mock_calls[-2][2]["timeout"] == 30.0  # then a refresh

    # Fire-and-forget from an automation works too.
    await hass.services.async_call(DOMAIN, "download_best", {"query": "ok computer"}, blocking=True)


async def test_download_best_no_match(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(f"{BASE}/download-best", status=404, json={"detail": "No album"})
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(DOMAIN, "download_best", {"query": "nothing"}, blocking=True)
    assert err.value.translation_key == "no_match"


async def test_actions_report_app_errors(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    detail = {"detail": "Must be logged in"}
    aioclient_mock.post(f"{BASE}/search-and-wait", status=409, json=detail)
    aioclient_mock.post(f"{BASE}/download-best", status=409, json=detail)
    with pytest.raises(HomeAssistantError, match="Must be logged in"):
        await hass.services.async_call(
            DOMAIN, "search", {"query": "x y"}, blocking=True, return_response=True
        )
    with pytest.raises(HomeAssistantError, match="Must be logged in"):
        await hass.services.async_call(DOMAIN, "download_best", {"query": "x y"}, blocking=True)


async def test_actions_need_a_loaded_entry(hass: HomeAssistant) -> None:
    from homeassistant.setup import async_setup_component

    assert await async_setup_component(hass, DOMAIN, {})
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN, "search", {"query": "ok computer"}, blocking=True, return_response=True
        )
    assert err.value.translation_key == "not_loaded"
