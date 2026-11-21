from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from ha_music_manager.api import create_app
from ha_music_manager.config import Settings
from ha_music_manager.downloads import group_state
from ha_music_manager.slskd_client import SlskdClient
from tests.conftest import search_file, search_response

SLSKD = "http://slskd.test/api/v0"


@pytest.fixture
def slskd() -> Iterator[respx.MockRouter]:
    with respx.mock(base_url=SLSKD, assert_all_called=False) as router:
        yield router


@pytest.fixture
def client(slskd: respx.MockRouter) -> Iterator[TestClient]:
    settings = Settings(soulseek_username="juan", slskd_url="http://slskd.test")
    app = create_app(settings, SlskdClient("http://slskd.test", "k" * 32))
    with TestClient(app) as c:
        yield c


def test_status(client: TestClient, slskd: respx.MockRouter) -> None:
    slskd.get("/application").respond(
        json={"server": {"state": "Connected, LoggedIn", "isConnected": True, "isLoggedIn": True}}
    )
    body = client.get("/api/status").json()
    assert body["engine"] == "external"
    assert body["logged_in"] is True
    assert body["username"] == "juan"


def test_engine_starting_is_503(client: TestClient, slskd: respx.MockRouter) -> None:
    slskd.get("/application").mock(side_effect=httpx.ConnectError("refused"))
    response = client.get("/api/status")
    assert response.status_code == 503


def test_upstream_errors_are_mapped(client: TestClient, slskd: respx.MockRouter) -> None:
    slskd.get("/searches/missing").respond(404)
    slskd.get("/searches/boom").respond(500)
    assert client.get("/api/searches/missing").status_code == 404
    assert client.get("/api/searches/boom").status_code == 502
    slskd.post("/searches").respond(409, json="Must be connected and logged in")
    response = client.post("/api/searches", json={"query": "anything"})
    assert response.status_code == 409
    assert response.json()["detail"] == "Must be connected and logged in"


def test_search_flow(client: TestClient, slskd: respx.MockRouter) -> None:
    start = slskd.post("/searches").respond(
        json={"id": "s1", "searchText": "ok computer", "state": "InProgress"}
    )
    response = client.post("/api/searches", json={"query": "  ok computer "})
    assert response.status_code == 201 and response.json() == {"id": "s1"}
    sent = json.loads(start.calls.last.request.content)
    assert sent["searchText"] == "ok computer"
    assert start.calls.last.request.headers["X-API-Key"] == "k" * 32

    slskd.get("/searches/s1").respond(
        json={
            "id": "s1",
            "searchText": "ok computer",
            "state": "Completed",
            "isComplete": True,
            "responseCount": 1,
        }
    )
    slskd.get("/searches/s1/responses").respond(
        json=[search_response("alice", [search_file("OK Computer\\01 Airbag.flac")])]
    )
    body = client.get("/api/searches/s1").json()
    assert body["complete"] is True
    assert body["albums"][0]["title"] == "OK Computer"

    slskd.delete("/searches/s1").respond(204)
    assert client.delete("/api/searches/s1").status_code == 204


def test_search_validation(client: TestClient) -> None:
    assert client.post("/api/searches", json={"query": "a"}).status_code == 422


def test_download_enqueues_with_encoded_username(
    client: TestClient, slskd: respx.MockRouter
) -> None:
    route = slskd.post("/transfers/downloads/dj%20bob").respond(201)
    response = client.post(
        "/api/downloads",
        json={"username": "dj bob", "files": [{"filename": "A\\1.flac", "size": 10}]},
    )
    assert response.status_code == 202
    assert json.loads(route.calls.last.request.content) == [{"filename": "A\\1.flac", "size": 10}]


def test_downloads_are_grouped_by_folder(client: TestClient, slskd: respx.MockRouter) -> None:
    def transfer(i: str, state: str, done: int) -> dict[str, object]:
        return {
            "id": i,
            "username": "alice",
            "filename": f"Music\\Album\\{i}.flac",
            "size": 100,
            "state": state,
            "bytesTransferred": done,
            "percentComplete": done,
        }

    slskd.get("/transfers/downloads").respond(
        json=[
            {
                "username": "alice",
                "directories": [
                    {
                        "directory": "Music\\Album",
                        "files": [
                            transfer("1", "Completed, Succeeded", 100),
                            transfer("2", "InProgress", 50),
                        ],
                    },
                    {"directory": "Empty", "files": []},
                ],
            }
        ]
    )
    [group] = client.get("/api/downloads").json()
    assert group["title"] == "Album"
    assert group["percent"] == 75.0
    assert group["state"] == "downloading"
    assert [f["name"] for f in group["files"]] == ["1.flac", "2.flac"]


def test_cancel_and_clear(client: TestClient, slskd: respx.MockRouter) -> None:
    cancel = slskd.delete("/transfers/downloads/alice/t1").respond(204)
    slskd.delete("/transfers/downloads/all/completed").respond(204)
    assert client.delete("/api/downloads/alice/t1").status_code == 204
    assert cancel.calls.last.request.url.params["remove"] == "true"
    assert client.delete("/api/downloads/completed").status_code == 204


def test_unknown_api_path_is_404(client: TestClient) -> None:
    assert client.get("/api/nope").status_code == 404


@pytest.mark.parametrize(
    ("states", "expected"),
    [
        (["Queued, Remotely", "Completed, Succeeded"], "queued"),
        (["InProgress", "Queued, Locally"], "downloading"),
        (["Completed, Succeeded"], "completed"),
        (["Completed, Succeeded", "Completed, Errored"], "failed"),
    ],
)
def test_group_state(states: list[str], expected: str) -> None:
    assert group_state(states) == expected


def test_ingress_only_needs_the_integration_key(
    tmp_path: Path, slskd: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    slskd.get("/application").respond(json={"server": {}})
    settings = Settings(slskd_url="http://slskd.test", ingress_only=True, data_dir=tmp_path)
    app = create_app(settings, SlskdClient("http://slskd.test", "k" * 32))
    key = (tmp_path / "integration_key").read_text()
    with TestClient(app) as c:
        assert c.get("/api/status").status_code == 403
        wrong = {"Authorization": "Bearer nope"}
        assert c.get("/api/status", headers=wrong).status_code == 403
        right = {"Authorization": f"Bearer {key}"}
        assert c.get("/api/status", headers=right).status_code == 200


def complete_search(slskd: respx.MockRouter, responses: list[dict[str, object]]) -> None:
    search = {"id": "s9", "searchText": "q", "state": "Completed", "isComplete": True}
    slskd.post("/searches").respond(json=search)
    slskd.get("/searches/s9/responses").respond(json=responses)
    slskd.delete("/searches/s9").respond(204)


ALBUMS = [
    search_response("fast", [search_file(f"MP3 Album\\{i}.mp3", bitRate=320) for i in range(10)]),
    search_response(
        "slow",
        [search_file(f"FLAC Album\\{i}.flac") for i in range(10)],
        hasFreeUploadSlot=False,
        queueLength=10,
        uploadSpeed=50_000,
    ),
    search_response("tiny", [search_file("Single\\1.flac")]),
]


def test_search_and_wait_filters_and_limits(client: TestClient, slskd: respx.MockRouter) -> None:
    complete_search(slskd, ALBUMS)
    body = client.post("/api/search-and-wait", json={"query": "album", "limit": 2}).json()
    assert body["response_count"] == 3
    assert len(body["albums"]) == 2
    assert "tracks" not in body["albums"][0]

    body = client.post(
        "/api/search-and-wait", json={"query": "album", "lossless_only": True, "min_tracks": 5}
    ).json()
    assert [a["title"] for a in body["albums"]] == ["FLAC Album"]
    assert body["albums"][0]["track_count"] == 10


def test_download_best_enqueues_the_top_match(client: TestClient, slskd: respx.MockRouter) -> None:
    complete_search(slskd, ALBUMS)
    enqueue = slskd.post("/transfers/downloads/slow").respond(201)
    response = client.post(
        "/api/download-best", json={"query": "album", "lossless_only": True, "min_tracks": 2}
    )
    assert response.status_code == 202
    assert response.json()["album"]["username"] == "slow"
    assert len(json.loads(enqueue.calls.last.request.content)) == 10


def test_download_best_404_when_nothing_matches(
    client: TestClient, slskd: respx.MockRouter
) -> None:
    complete_search(slskd, ALBUMS)
    response = client.post("/api/download-best", json={"query": "album", "min_tracks": 50})
    assert response.status_code == 404
    assert "No album matched" in response.json()["detail"]


def test_overview(client: TestClient, slskd: respx.MockRouter) -> None:
    slskd.get("/application").respond(
        json={"server": {"state": "Connected, LoggedIn", "isConnected": True, "isLoggedIn": True}}
    )
    slskd.get("/transfers/downloads").respond(
        json=[
            {
                "username": "alice",
                "directories": [
                    {
                        "directory": "Music\\Album",
                        "files": [
                            {
                                "id": "1",
                                "username": "alice",
                                "filename": "Music\\Album\\1.flac",
                                "size": 100,
                                "state": "InProgress",
                                "bytesTransferred": 40,
                                "averageSpeed": 1500.0,
                            },
                            {
                                "id": "2",
                                "username": "alice",
                                "filename": "Music\\Album\\2.flac",
                                "size": 100,
                                "state": "Queued, Remotely",
                            },
                        ],
                    }
                ],
            }
        ]
    )
    body = client.get("/api/overview").json()
    assert body["status"]["logged_in"] is True
    assert body["stats"] == {
        "active_albums": 1,
        "queued_files": 1,
        "downloading_files": 1,
        "completed_albums": 0,
        "failed_albums": 0,
        "speed": 1500.0,
    }
    assert body["downloads"] == [
        {
            "username": "alice",
            "directory": "Music\\Album",
            "title": "Album",
            "state": "downloading",
            "percent": 20.0,
            "file_count": 2,
        }
    ]
