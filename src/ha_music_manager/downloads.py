"""Download progress, grouped per album folder like the search results."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from ha_music_manager.albums import split_path
from ha_music_manager.slskd_models import UserTransfers

GroupState = Literal["queued", "downloading", "completed", "failed"]


class DownloadFile(BaseModel):
    id: str
    name: str
    state: str
    size: int
    percent: float
    speed: float
    error: str | None


class DownloadGroup(BaseModel):
    username: str
    directory: str
    title: str
    percent: float
    state: GroupState
    files: list[DownloadFile]


class DownloadStats(BaseModel):
    active_albums: int  # queued or downloading
    queued_files: int
    downloading_files: int
    completed_albums: int
    failed_albums: int
    speed: float  # bytes/s, all running transfers


def group_state(states: list[str]) -> GroupState:
    """slskd states look like "Queued, Remotely", "InProgress", "Completed, Succeeded"."""
    if any(s.startswith("InProgress") or s.startswith("Initializing") for s in states):
        return "downloading"
    if all(s.startswith("Completed") for s in states):
        succeeded = all(s.endswith("Succeeded") for s in states)
        return "completed" if succeeded else "failed"
    return "queued"


def build_groups(users: list[UserTransfers]) -> list[DownloadGroup]:
    groups: list[DownloadGroup] = []
    for user in users:
        for directory in user.directories:
            if not directory.files:
                continue
            total = sum(f.size for f in directory.files) or 1
            done = sum(f.bytes_transferred for f in directory.files)
            groups.append(
                DownloadGroup(
                    username=user.username,
                    directory=directory.directory,
                    title=directory.directory.replace("/", "\\").rpartition("\\")[2],
                    percent=round(100 * done / total, 1),
                    state=group_state([f.state for f in directory.files]),
                    files=[
                        DownloadFile(
                            id=f.id,
                            name=split_path(f.filename)[1],
                            state=f.state,
                            size=f.size,
                            percent=round(f.percent_complete, 1),
                            speed=f.average_speed,
                            error=f.exception,
                        )
                        for f in directory.files
                    ],
                )
            )
    return groups


def stats(groups: list[DownloadGroup]) -> DownloadStats:
    files = [f for g in groups for f in g.files]
    running = [f for f in files if f.state.startswith("InProgress")]
    return DownloadStats(
        active_albums=sum(g.state in ("queued", "downloading") for g in groups),
        queued_files=sum(f.state.startswith("Queued") for f in files),
        downloading_files=len(running),
        completed_albums=sum(g.state == "completed" for g in groups),
        failed_albums=sum(g.state == "failed" for g in groups),
        speed=round(sum(f.speed for f in running), 1),
    )
