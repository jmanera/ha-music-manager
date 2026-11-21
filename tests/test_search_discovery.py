from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from ha_music_manager import discovery
from ha_music_manager.search import run_search
from ha_music_manager.slskd_client import SlskdClient
from tests.conftest import search_file, search_response

SLSKD = "http://slskd.test/api/v0"


async def test_run_search_polls_until_complete_and_cleans_up() -> None:
    with respx.mock(base_url=SLSKD) as slskd:
        slskd.post("/searches").respond(json={"id": "s", "searchText": "q", "state": "InProgress"})
        slskd.get("/searches/s").mock(
            side_effect=[
                httpx.Response(200, json={"id": "s", "searchText": "q", "state": "InProgress"}),
                httpx.Response(
                    200, json={"id": "s", "searchText": "q", "state": "Done", "isComplete": True}
                ),
            ]
        )
        slskd.get("/searches/s/responses").respond(
            json=[search_response("u", [search_file("A\\1.flac")])]
        )
        cleanup = slskd.delete("/searches/s").respond(204)
        client = SlskdClient("http://slskd.test", "k" * 32)
        count, albums = await run_search(client, "q", search_seconds=5, poll_interval=0)
        await client.aclose()
        sent = json.loads(slskd.calls[0].request.content)
    assert count == 1 and albums[0].title == "A"
    assert cleanup.called
    assert sent["searchTimeout"] == 5000


async def test_run_search_gives_up_after_the_deadline() -> None:
    with respx.mock(base_url=SLSKD, assert_all_called=False) as slskd:
        slskd.post("/searches").respond(json={"id": "s", "searchText": "q", "state": "InProgress"})
        slskd.get("/searches/s").respond(json={"id": "s", "searchText": "q", "state": "InProgress"})
        slskd.get("/searches/s/responses").respond(json=[])
        slskd.delete("/searches/s").respond(500)  # cleanup errors are ignored
        client = SlskdClient("http://slskd.test", "k" * 32)
        count, albums = await run_search(client, "q", search_seconds=-4.99, poll_interval=0)
        await client.aclose()
    assert (count, albums) == (0, [])


def test_integration_key_is_created_once(tmp_path: Path) -> None:
    key = discovery.integration_key(tmp_path / "data")
    assert len(key) >= 32
    assert discovery.integration_key(tmp_path / "data") == key
    assert (tmp_path / "data" / "integration_key").stat().st_mode & 0o777 == 0o600
    (tmp_path / "data" / "integration_key").write_text("short")
    assert discovery.integration_key(tmp_path / "data") != "short"


async def test_announce_skips_outside_the_supervisor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    assert await discovery.announce(8099, "key") is False


async def test_announce_posts_host_port_and_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPERVISOR_TOKEN", "sup")
    monkeypatch.setattr(discovery.socket, "gethostname", lambda: "abc123-music-manager")
    with respx.mock(base_url="http://supervisor") as supervisor:
        route = supervisor.post("/discovery").mock(
            side_effect=[httpx.Response(500), httpx.Response(200, json={"result": "ok"})]
        )
        assert await discovery.announce(8099, "key", retry_delay=0) is True
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer sup"
    assert json.loads(request.content) == {
        "service": "music_manager",
        "config": {"host": "abc123-music-manager", "port": 8099, "api_key": "key"},
    }


async def test_announce_gives_up(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPERVISOR_TOKEN", "sup")
    with respx.mock(base_url="http://supervisor") as supervisor:
        supervisor.post("/discovery").mock(side_effect=httpx.ConnectError("down"))
        assert await discovery.announce(8099, "key", attempts=2, retry_delay=0) is False
