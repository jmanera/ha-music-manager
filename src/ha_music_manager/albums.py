"""Turn slskd's flat per-user file lists into ranked album candidates.

Soulseek search results are files. People looking for music want albums, so we group each
peer's files by folder, keep only audio, summarise the quality and rank the candidates by
how good *and* how likely to actually download they are.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from statistics import median

from pydantic import BaseModel

from ha_music_manager.slskd_models import SearchFile, SearchResponse

AUDIO_EXTENSIONS = frozenset(
    {"flac", "alac", "ape", "wv", "wav", "aiff", "aif", "mp3", "m4a", "aac", "ogg", "opus"}
)
LOSSLESS_EXTENSIONS = frozenset({"flac", "alac", "ape", "wv", "wav", "aiff", "aif"})
# "CD1", "Disc 2", "Disk-3": shown together with the parent folder, which names the album.
_DISC_FOLDER = re.compile(r"^(cd|dis[ck])[\s_-]*\d+$", re.IGNORECASE)


class Track(BaseModel):
    filename: str  # full Soulseek path, needed to enqueue the download
    name: str
    size: int
    extension: str
    bit_rate: int | None
    length: int | None


class AlbumSummary(BaseModel):
    """An album without its track list: what automations and Home Assistant get."""

    username: str
    directory: str
    title: str
    track_count: int
    quality: str
    lossless: bool
    total_size: int
    total_length: int
    has_free_upload_slot: bool
    queue_length: int
    upload_speed: int
    score: float


class AlbumCandidate(AlbumSummary):
    tracks: list[Track]

    def summary(self) -> AlbumSummary:
        return AlbumSummary.model_validate(self.model_dump(exclude={"tracks"}))


def split_path(filename: str) -> tuple[str, str]:
    """Soulseek paths use backslashes regardless of the peer's OS."""
    directory, _, name = filename.replace("/", "\\").rpartition("\\")
    return directory, name


def extension_of(file: SearchFile) -> str:
    ext = file.extension or file.filename.rpartition(".")[2]
    return ext.lower().lstrip(".")


def album_title(directory: str) -> str:
    parts = [p for p in directory.split("\\") if p]
    if not parts:
        return directory
    if _DISC_FOLDER.match(parts[-1]) and len(parts) > 1:
        return f"{parts[-2]} / {parts[-1]}"
    return parts[-1]


def quality_label(files: list[SearchFile]) -> tuple[str, bool]:
    """A short label like "FLAC 24/96", "FLAC" or "MP3 320", plus whether it's lossless."""
    extensions = {extension_of(f) for f in files}
    lossless = extensions <= LOSSLESS_EXTENSIONS
    main = max(extensions, key=lambda e: sum(extension_of(f) == e for f in files))
    fmt = main.upper()
    if len(extensions) > 1:
        fmt += "+"
    if lossless:
        depth = max((f.bit_depth or 0) for f in files)
        rate = max((f.sample_rate or 0) for f in files)
        if depth > 16 or rate > 48000:
            return f"{fmt} {depth or '?'}/{rate / 1000:g}", True
        return fmt, True
    rates = [f.bit_rate for f in files if f.bit_rate]
    return (f"{fmt} {round(median(rates))}" if rates else fmt), False


def score(
    lossless: bool,
    bit_rate: float | None,
    has_free_upload_slot: bool,
    queue_length: int,
    upload_speed: int,
) -> float:
    """0-100. Half quality, half "will this finish soon"."""
    quality = 50.0 if lossless else 40.0 * min((bit_rate or 128) / 320, 1.0)
    availability = 20.0 if has_free_upload_slot else 0.0
    availability -= min(queue_length, 50) * 0.4
    # 0 at 10 KB/s, full 30 points at ~10 MB/s.
    speed = max(upload_speed, 1)
    availability += 30.0 * min(max(math.log10(speed / 10_000) / 3, 0.0), 1.0)
    return round(max(quality + availability, 0.0), 1)


def group_albums(responses: list[SearchResponse], min_tracks: int = 1) -> list[AlbumCandidate]:
    candidates: list[AlbumCandidate] = []
    for response in responses:
        folders: dict[str, list[SearchFile]] = defaultdict(list)
        for file in response.files:
            if extension_of(file) in AUDIO_EXTENSIONS and not file.is_locked:
                folders[split_path(file.filename)[0]].append(file)

        for directory, files in folders.items():
            if len(files) < min_tracks:
                continue
            files.sort(key=lambda f: f.filename.lower())
            label, lossless = quality_label(files)
            rates = [f.bit_rate for f in files if f.bit_rate]
            candidates.append(
                AlbumCandidate(
                    username=response.username,
                    directory=directory,
                    title=album_title(directory),
                    track_count=len(files),
                    tracks=[
                        Track(
                            filename=f.filename,
                            name=split_path(f.filename)[1],
                            size=f.size,
                            extension=extension_of(f),
                            bit_rate=f.bit_rate,
                            length=f.length,
                        )
                        for f in files
                    ],
                    quality=label,
                    lossless=lossless,
                    total_size=sum(f.size for f in files),
                    total_length=sum(f.length or 0 for f in files),
                    has_free_upload_slot=response.has_free_upload_slot,
                    queue_length=response.queue_length,
                    upload_speed=response.upload_speed,
                    score=score(
                        lossless,
                        median(rates) if rates else None,
                        response.has_free_upload_slot,
                        response.queue_length,
                        response.upload_speed,
                    ),
                )
            )
    candidates.sort(key=lambda a: (-a.score, -len(a.tracks), a.title.lower()))
    return candidates
