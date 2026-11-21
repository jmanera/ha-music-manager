"""Blocking-style searches for automations: search, wait for the results, optionally pick one."""

from __future__ import annotations

import asyncio
import contextlib
import time

from pydantic import BaseModel, Field

from ha_music_manager.albums import AlbumCandidate, group_albums
from ha_music_manager.slskd_client import SlskdClient


class AlbumFilters(BaseModel):
    lossless_only: bool = False
    free_slot_only: bool = False
    min_tracks: int = Field(default=1, ge=1, le=100)


def filter_albums(albums: list[AlbumCandidate], filters: AlbumFilters) -> list[AlbumCandidate]:
    return [
        a
        for a in albums
        if a.track_count >= filters.min_tracks
        and (a.lossless or not filters.lossless_only)
        and (a.has_free_upload_slot or not filters.free_slot_only)
    ]


async def run_search(
    client: SlskdClient, query: str, search_seconds: float, poll_interval: float = 1.0
) -> tuple[int, list[AlbumCandidate]]:
    """Search, wait until slskd finishes (it stops on its own after `search_seconds`), clean up.

    Returns the number of peers that answered and the ranked albums.
    """
    search = await client.start_search(query, timeout_ms=int(search_seconds * 1000))
    deadline = time.monotonic() + search_seconds + 5
    try:
        while not search.is_complete and time.monotonic() < deadline:
            await asyncio.sleep(poll_interval)
            search = await client.get_search(search.id)
        responses = await client.get_responses(search.id)
    finally:
        with contextlib.suppress(Exception):
            await client.delete_search(search.id)
    return len(responses), group_albums(responses)


async def download_album(client: SlskdClient, album: AlbumCandidate) -> None:
    await client.enqueue(album.username, [(t.filename, t.size) for t in album.tracks])
