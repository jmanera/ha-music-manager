"""End-to-end check: a real Home Assistant talks to the real app image (with a fake slskd).

Run through `make e2e`, which starts the containers. Fresh Home Assistant only: it onboards a
throwaway user, sets the integration up through the config flow REST API, then exercises the
actions, sensors and events the way an automation would.
"""

from __future__ import annotations

import asyncio
import os
import secrets
import sys
import time
from typing import Any

import aiohttp

HA = os.environ.get("E2E_HA_URL", "http://localhost:18123")
APP_HOST = os.environ.get("E2E_APP_HOST", "music-app")
APP_KEY = os.environ["E2E_APP_KEY"]
CLIENT_ID = f"{HA}/"


def check(condition: bool, message: str) -> None:
    print(("  ok    " if condition else "  FAIL  ") + message)
    if not condition:
        sys.exit(1)


async def wait_for_ha(http: aiohttp.ClientSession) -> None:
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        try:
            async with http.get(f"{HA}/api/onboarding") as response:
                if response.status == 200:
                    return
        except aiohttp.ClientError:
            pass
        await asyncio.sleep(2)
    sys.exit("Home Assistant did not start")


async def onboard(http: aiohttp.ClientSession) -> str:
    """Create the owner account of the throwaway instance and return an access token."""
    user = {
        "client_id": CLIENT_ID,
        "name": "E2E",
        "username": "e2e",
        "password": secrets.token_urlsafe(16),
        "language": "en",
    }
    async with http.post(f"{HA}/api/onboarding/users", json=user) as response:
        response.raise_for_status()
        code = (await response.json())["auth_code"]
    form = {"grant_type": "authorization_code", "code": code, "client_id": CLIENT_ID}
    async with http.post(f"{HA}/auth/token", data=form) as response:
        response.raise_for_status()
        token: str = (await response.json())["access_token"]
    return token


async def main() -> None:
    async with aiohttp.ClientSession() as http:
        print("Waiting for Home Assistant…")
        await wait_for_ha(http)
        token = await onboard(http)
        auth = {"Authorization": f"Bearer {token}"}

        async def api(method: str, path: str, body: Any = None) -> Any:
            async with http.request(method, f"{HA}/api/{path}", json=body, headers=auth) as r:
                payload = await r.json(content_type=None)
                if r.status >= 400:
                    raise RuntimeError(f"{method} {path}: {r.status} {payload}")
                return payload

        print("Config flow")
        flow = await api("POST", "config/config_entries/flow", {"handler": "music_manager"})
        check(flow.get("step_id") == "user", "the integration loads and shows the user step")
        bad = await api(
            "POST",
            f"config/config_entries/flow/{flow['flow_id']}",
            {"host": APP_HOST, "port": 8099, "api_key": "wrong-key"},
        )
        check(bad.get("errors") == {"base": "invalid_auth"}, "a wrong key is rejected by the app")
        done = await api(
            "POST",
            f"config/config_entries/flow/{flow['flow_id']}",
            {"host": APP_HOST, "port": 8099, "api_key": APP_KEY},
        )
        check(done.get("type") == "create_entry", "the real key creates the entry")

        await asyncio.sleep(3)
        state = await api("GET", "states/binary_sensor.music_manager_soulseek_connection")
        check(state["state"] == "on", "binary sensor reports the Soulseek login")
        speed = await api("GET", "states/sensor.music_manager_download_speed")
        check(speed["attributes"].get("unit_of_measurement") == "MB/s", "speed sensor in MB/s")

        print("Actions")
        found = await api(
            "POST",
            "services/music_manager/search?return_response",
            {"query": "midnight ferns lanterns", "search_time": 5, "lossless_only": True},
        )
        albums = found["service_response"]["albums"]
        check(len(albums) == 2 and all(a["lossless"] for a in albums), "search filters lossless")
        check(albums[0]["quality"] == "FLAC 24/96", "best album first")

        async with http.ws_connect(f"{HA}/api/websocket") as ws:
            await ws.receive_json()
            await ws.send_json({"type": "auth", "access_token": token})
            check((await ws.receive_json())["type"] == "auth_ok", "websocket authenticated")
            await ws.send_json(
                {
                    "id": 1,
                    "type": "subscribe_events",
                    "event_type": "music_manager_download_completed",
                }
            )
            await ws.receive_json()

            chosen = await api(
                "POST",
                "services/music_manager/download_best?return_response",
                {"query": "midnight ferns lanterns", "search_time": 5, "min_tracks": 5},
            )
            album = chosen["service_response"]["album"]
            check(album["title"] == "2019 - Lanterns", "download_best picks the top album")

            print("Events (fake downloads take ~20 s)")
            try:
                async with asyncio.timeout(90):
                    while True:
                        message = await ws.receive_json()
                        if message.get("type") == "event":
                            event = message["event"]
                            break
            except TimeoutError:
                check(False, "download_completed event within 90 s")
            check(event["data"]["title"] == "2019 - Lanterns", "completed event for the album")
            check(event["data"]["file_count"] == 9, "event carries the file count")

        await asyncio.sleep(1)
        completed = await api("GET", "states/sensor.music_manager_completed_albums")
        check(completed["state"] == "1", "completed albums sensor updated")
        print("End-to-end test passed")


if __name__ == "__main__":
    asyncio.run(main())
