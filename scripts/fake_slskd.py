"""A stand-in for slskd's API with canned results, for UI work and screenshots (`make demo`).

Searches "find" a few made-up albums over a couple of seconds; downloads progress on their own.
"""

from __future__ import annotations

import itertools
import os
import time
from typing import Any

import uvicorn
from fastapi import FastAPI

app = FastAPI()
searches: dict[str, dict[str, Any]] = {}
downloads: dict[str, dict[str, Any]] = {}
_ids = itertools.count(1)

ALBUMS = [
    # (user, folder, ext, bitrate, depth, rate, tracks, free slot, queue, speed)
    (
        "vinyl_owl",
        "Music\\The Midnight Ferns\\2019 - Lanterns",
        "flac",
        None,
        24,
        96000,
        9,
        True,
        0,
        6_400_000,
    ),
    (
        "bytebandit",
        "share\\The Midnight Ferns - Lanterns (2019)",
        "flac",
        None,
        16,
        44100,
        9,
        True,
        2,
        1_900_000,
    ),
    ("deep_crate", "mp3\\Midnight Ferns\\Lanterns", "mp3", 320, None, None, 9, False, 34, 350_000),
    (
        "lofi_lou",
        "Albums\\The Midnight Ferns\\Lanterns\\CD1",
        "mp3",
        245,
        None,
        None,
        5,
        True,
        0,
        900_000,
    ),
    (
        "lofi_lou",
        "Albums\\The Midnight Ferns\\Lanterns\\CD2",
        "mp3",
        245,
        None,
        None,
        4,
        True,
        0,
        900_000,
    ),
    ("tape_hiss", "music\\ferns\\singles", "ogg", 192, None, None, 2, False, 120, 40_000),
]
TITLES = [
    "Paper Moon",
    "Static Garden",
    "Low Tide",
    "Glasshouse",
    "Northbound",
    "Ember",
    "Quiet Engines",
    "Saltwater",
    "Lanterns",
]


def responses() -> list[dict[str, Any]]:
    by_user: dict[str, dict[str, Any]] = {}
    for user, folder, ext, br, depth, rate, n, free, queue, speed in ALBUMS:
        entry = by_user.setdefault(
            user,
            {
                "username": user,
                "files": [],
                "hasFreeUploadSlot": free,
                "queueLength": queue,
                "uploadSpeed": speed,
            },
        )
        size = 32_000_000 if ext == "flac" else 9_000_000
        entry["files"] += [
            {
                "filename": f"{folder}\\{i:02d} {TITLES[(i - 1) % 9]}.{ext}",
                "size": size,
                "extension": ext,
                "bitRate": br,
                "bitDepth": depth,
                "sampleRate": rate,
                "length": 180 + 17 * i,
            }
            for i in range(1, n + 1)
        ] + [{"filename": f"{folder}\\cover.jpg", "size": 300_000, "extension": "jpg"}]
    return list(by_user.values())


@app.get("/api/v0/application")
def application() -> dict[str, Any]:
    return {"server": {"state": "Connected, LoggedIn", "isConnected": True, "isLoggedIn": True}}


@app.post("/api/v0/searches")
def start_search(body: dict[str, Any]) -> dict[str, Any]:
    searches[body["id"]] = {"id": body["id"], "searchText": body["searchText"], "at": time.time()}
    return {**searches[body["id"]], "state": "InProgress"}


def _visible(search_id: str) -> list[dict[str, Any]]:
    elapsed = time.time() - searches[search_id]["at"]
    return responses()[: min(int(elapsed * 2) + 1, 99)]


@app.get("/api/v0/searches/{search_id}")
def get_search(search_id: str) -> dict[str, Any]:
    complete = time.time() - searches[search_id]["at"] > 3
    return {
        **searches[search_id],
        "state": "Completed" if complete else "InProgress",
        "isComplete": complete,
        "responseCount": len(_visible(search_id)),
    }


@app.get("/api/v0/searches/{search_id}/responses")
def get_responses(search_id: str) -> list[dict[str, Any]]:
    return _visible(search_id)


@app.delete("/api/v0/searches/{search_id}", status_code=204)
def delete_search(search_id: str) -> None:
    searches.pop(search_id, None)


@app.post("/api/v0/transfers/downloads/{username}", status_code=201)
def enqueue(username: str, files: list[dict[str, Any]]) -> None:
    for i, f in enumerate(files):
        tid = str(next(_ids))
        downloads[tid] = {"id": tid, "username": username, **f, "at": time.time() + i * 1.5}


@app.get("/api/v0/transfers/downloads")
def list_downloads() -> list[dict[str, Any]]:
    users: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for d in downloads.values():
        pct = max(0.0, min((time.time() - d["at"]) / 6 * 100, 100.0))
        state = (
            "Queued, Remotely"
            if pct == 0
            else "InProgress"
            if pct < 100
            else "Completed, Succeeded"
        )
        folder = d["filename"].rpartition("\\")[0]
        users.setdefault(d["username"], {}).setdefault(folder, []).append(
            {
                "id": d["id"],
                "username": d["username"],
                "filename": d["filename"],
                "size": d["size"],
                "state": state,
                "percentComplete": pct,
                "bytesTransferred": int(d["size"] * pct / 100),
                "averageSpeed": 2_500_000.0 if state == "InProgress" else 0.0,
            }
        )
    return [
        {"username": u, "directories": [{"directory": k, "files": v} for k, v in dirs.items()]}
        for u, dirs in users.items()
    ]


@app.delete("/api/v0/transfers/downloads/all/completed", status_code=204)
def clear_completed() -> None:
    for tid in [t for t, d in downloads.items() if time.time() - d["at"] >= 6]:
        del downloads[tid]


@app.delete("/api/v0/transfers/downloads/{username}/{transfer_id}", status_code=204)
def cancel(username: str, transfer_id: str) -> None:
    downloads.pop(transfer_id, None)


if __name__ == "__main__":
    host = os.environ.get("FAKE_SLSKD_HOST", "127.0.0.1")  # 0.0.0.0 in the e2e containers
    uvicorn.run(app, host=host, port=5031, log_level="warning")
