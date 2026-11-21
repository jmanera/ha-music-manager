from __future__ import annotations

import pytest

from ha_music_manager.albums import album_title, group_albums, quality_label, score, split_path
from ha_music_manager.slskd_models import SearchFile, SearchResponse
from tests.conftest import search_file, search_response

OK = "Music\\Radiohead\\1997 - OK Computer"


def responses(*raw: dict[str, object]) -> list[SearchResponse]:
    return [SearchResponse.model_validate(r) for r in raw]


def files(*raw: dict[str, object]) -> list[SearchFile]:
    return [SearchFile.model_validate(r) for r in raw]


def test_split_path_handles_both_separators() -> None:
    assert split_path(f"{OK}\\01 Airbag.flac") == (OK, "01 Airbag.flac")
    assert split_path("a/b/c.mp3") == ("a\\b", "c.mp3")
    assert split_path("loose.mp3") == ("", "loose.mp3")


@pytest.mark.parametrize(
    ("directory", "title"),
    [
        (OK, "1997 - OK Computer"),
        ("Music\\Pink Floyd - The Wall\\CD2", "Pink Floyd - The Wall / CD2"),
        ("Music\\Album\\Disc 1", "Album / Disc 1"),
        ("CD1", "CD1"),
        ("", ""),
    ],
)
def test_album_title(directory: str, title: str) -> None:
    assert album_title(directory) == title


def test_quality_label_lossless_hires_and_cd() -> None:
    hires = files(search_file("a.flac", bitDepth=24, sampleRate=96000))
    cd = files(search_file("a.flac", bitDepth=16, sampleRate=44100))
    assert quality_label(hires) == ("FLAC 24/96", True)
    assert quality_label(cd) == ("FLAC", True)


def test_quality_label_lossy_uses_median_bitrate_and_flags_mixed_formats() -> None:
    mp3 = files(*(search_file(f"{i}.mp3", bitRate=b) for i, b in enumerate([320, 320, 256])))
    assert quality_label(mp3) == ("MP3 320", False)
    mixed = files(search_file("1.mp3", bitRate=192), search_file("2.mp3"), search_file("3.m4a"))
    assert quality_label(mixed) == ("MP3+ 192", False)
    assert quality_label(files(search_file("1.ogg"))) == ("OGG", False)


def test_score_prefers_quality_and_availability() -> None:
    fast_flac = score(True, None, True, 0, 5_000_000)
    slow_flac = score(True, None, False, 40, 20_000)
    fast_mp3 = score(False, 320, True, 0, 5_000_000)
    assert fast_flac > fast_mp3 > slow_flac
    assert 0 <= slow_flac <= fast_flac <= 100
    assert score(False, None, False, 500, 0) == 0


def test_group_albums_groups_per_user_and_folder_and_skips_non_audio() -> None:
    result = group_albums(
        responses(
            search_response(
                "alice",
                [
                    search_file(f"{OK}\\02 Paranoid Android.flac"),
                    search_file(f"{OK}\\01 Airbag.flac", length=284),
                    search_file(f"{OK}\\cover.jpg"),
                    search_file(f"{OK}\\rip.log"),
                    search_file("Other\\single.mp3", bitRate=320),
                ],
            ),
            search_response("bob", [search_file(f"{OK}\\01 Airbag.mp3", bitRate=128)]),
        )
    )
    assert [(a.username, a.title, len(a.tracks)) for a in result] == [
        ("alice", "1997 - OK Computer", 2),
        ("alice", "Other", 1),
        ("bob", "1997 - OK Computer", 1),
    ]
    best = result[0]
    assert [t.name for t in best.tracks] == ["01 Airbag.flac", "02 Paranoid Android.flac"]
    assert best.lossless and best.quality == "FLAC"
    assert best.total_size == 60_000_000 and best.total_length == 284


def test_group_albums_drops_locked_files_and_small_folders() -> None:
    raw = search_response(
        "carol",
        [
            search_file("A\\1.flac", isLocked=True),
            search_file("B\\1.flac"),
            search_file("C\\1.flac"),
            search_file("C\\2.flac"),
        ],
    )
    assert [a.directory for a in group_albums(responses(raw), min_tracks=2)] == ["C"]
    assert group_albums([]) == []
