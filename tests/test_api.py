from __future__ import annotations

import json
from collections.abc import Iterator

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from ha_music_manager.api import create_app, group_state
from ha_music_manager.config import Settings
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


def test_ingress_only_rejects_other_clients() -> None:
    settings = Settings(slskd_url="http://slskd.test", ingress_only=True)
    app = create_app(settings, SlskdClient("http://slskd.test", "k" * 32))
    with TestClient(app) as c:
        assert c.get("/api/status").status_code == 403
