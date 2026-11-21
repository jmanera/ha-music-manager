# HA Music Manager

Search and download music from the [Soulseek](https://www.slsknet.org/) network without leaving
Home Assistant. It runs as a Home Assistant app with its own panel in the sidebar, and comes
with an integration that adds sensors, actions and events for your automations.

![Supports amd64](https://img.shields.io/badge/amd64-yes-green.svg)
![Supports aarch64](https://img.shields.io/badge/aarch64-yes-green.svg)
![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)
[![HACS: custom](https://img.shields.io/badge/HACS-custom-orange.svg)](https://hacs.xyz/)

![Album search and downloads](docs/screenshot.jpg)

Soulseek search results come back as thousands of loose files. HA Music Manager turns them
into **albums**: it groups each peer's files by folder, shows the format and bitrate at a
glance, and ranks the candidates by quality and by how likely they are to download quickly.
One click queues the whole album into your media folder. From there Music Assistant, Jellyfin
or Plex can pick it up.

> **Status:** early development (0.x). The app (search, album grouping, downloads) and the
> Home Assistant integration work. See the [roadmap](#roadmap).

## Features

- **Album-first search.** Results are grouped per peer and folder, with multi-disc folders
  (`CD1`, `Disc 2`) labelled after their parent.
- **Quality at a glance.** You see labels like `FLAC 24/96`, `FLAC` or `MP3 320`, plus a
  0–100 score that weighs quality against the peer's free slots, queue length and upload speed.
- **One-click downloads** into `/media/music`, with live progress per album and per track.
- **Native feel.** It lives in the Home Assistant sidebar through Ingress, follows your
  light/dark theme and works in the companion app.
- **Automations.** The integration adds download sensors, a Soulseek connection sensor,
  `music_manager.search` and `music_manager.download_best` actions, and events when an album
  finishes or fails.
- **Secure by default.** The Soulseek engine's API only listens on loopback behind a random API
  key. The app only answers Home Assistant's Ingress gateway and the integration's own key.

## Installation

1. In Home Assistant, go to **Settings → Apps → App store → ⋮ → Repositories** and add
   `https://github.com/jmanera/ha-music-manager`.
2. Install **Music Manager**, then set your Soulseek username and password under
   **Configuration**. A new account is created on first login if the name is free.
3. Start the app and open **Music** in the sidebar.

See [`music_manager/DOCS.md`](music_manager/DOCS.md) for all options.

### Integration (optional)

1. In [HACS](https://hacs.xyz/), open **⋮ → Custom repositories** and add
   `https://github.com/jmanera/ha-music-manager` with the type **Integration**.
2. Install **Music Manager** and restart Home Assistant.
3. Home Assistant finds the running app on its own: open **Settings → Devices & services** and
   click **Configure** on the discovered *Music Manager*. You don't need to type a host or a key.

Requires Home Assistant 2026.9 or newer.

## Home Assistant integration

| Entity | What it shows |
| --- | --- |
| `binary_sensor.music_manager_soulseek_connection` | On while logged in to Soulseek |
| `sensor.music_manager_active_albums` | Albums queued or downloading |
| `sensor.music_manager_queued_files` / `_downloading_files` | Files waiting / in progress |
| `sensor.music_manager_download_speed` | Total download speed |
| `sensor.music_manager_completed_albums` / `_failed_albums` | Finished albums still listed in the app |

**Actions**

- `music_manager.search` searches, waits for the results and returns the best albums as a
  response (title, quality, track count, peer, score). Filters: `lossless_only`,
  `free_slot_only`, `min_tracks`, `limit`, `search_time`.
- `music_manager.download_best` takes the same filters and downloads the top-ranked album
  that passes them. It returns the chosen album.

**Events**

- `music_manager_download_completed` and `music_manager_download_failed`, with `title`,
  `username`, `directory` and `file_count`.

### Example automations

Get a phone notification when an album finishes:

```yaml
triggers:
  - trigger: event
    event_type: music_manager_download_completed
actions:
  - action: notify.mobile_app_my_phone
    data:
      title: Album downloaded
      message: "{{ trigger.event.data.title }} ({{ trigger.event.data.file_count }} files)"
```

Ask Assist, a dashboard button or a script to fetch an album in lossless:

```yaml
script:
  get_album:
    fields:
      album:
        selector:
          text:
    sequence:
      - action: music_manager.download_best
        data:
          query: "{{ album }}"
          lossless_only: true
          min_tracks: 5
        response_variable: result
      - action: persistent_notification.create
        data:
          message: "Downloading {{ result.album.title }} ({{ result.album.quality }})"
```

## How it works

```
 Home Assistant sidebar            Music Manager integration
          │  Ingress (172.30.32.2)              │  bearer key, found through
          │                                     │  Supervisor discovery
          ▼                                     ▼ :8099
 ┌──────────── app container ───────────────────────────────┐
 │  FastAPI backend ── serves the Svelte UI                 │
 │     │  groups files into albums, scores them             │
 │     │  supervises ▼ (restarts on crash)                  │
 │     └─ HTTP + API key ─▶ slskd  127.0.0.1:5030 ──────────┼─▶ Soulseek network (:50300)
 │                            │                             │
 │                            └─▶ /media/music              │
 └──────────────────────────────────────────────────────────┘
```

- **[slskd](https://github.com/slskd/slskd)** is the Soulseek engine. The backend writes its
  config, runs it as a child process and talks to its REST API.
- **The backend** (`src/ha_music_manager`) is Python 3.13 with FastAPI, httpx and Pydantic,
  type-checked with `mypy --strict`.
- **The integration** (`custom_components/music_manager`) polls the app every 10 seconds
  through a `DataUpdateCoordinator`. On startup the app sends its hostname, port and a
  persistent key to the Supervisor's discovery API, so Home Assistant sets the integration up
  without any typing.
- **The frontend** (`frontend/`) is Svelte 5, TypeScript and Vite. It is built into static files
  and served by the backend. Every URL is relative, so it works behind Ingress' dynamic prefix.

## Development

You need [uv](https://docs.astral.sh/uv/), Node 20+ and Docker (optional). The integration is
tested against a real Home Assistant core (via `pytest-homeassistant-custom-component`) in its
own Python 3.14 environment, `integration_tests/`, so the app keeps its own dependency set.

```bash
make install        # Python + npm dependencies, pre-commit hooks
make check          # lint, types, tests (app, frontend, integration), security audit
make ha-test        # only the Home Assistant integration tests
make hassfest       # Home Assistant's official validator for the integration
make e2e            # real Home Assistant + app image + fake slskd, end to end (Docker)
make demo           # whole app on http://localhost:8099 with a fake slskd and canned results
make dev            # backend on :8099 against an slskd you run yourself (see Makefile)
make image          # build the app image locally
```

All tests run **locally** (`make check` and pre-commit), not in CI. GitHub Actions only builds
and publishes the multi-arch images on a version tag.

## Roadmap

- [x] **Phase 1.** slskd engine, album-oriented search, quality scoring, downloads with progress
- [x] **Phase 3.** Home Assistant integration: Supervisor discovery, sensors, `search` and
      `download_best` actions, completed/failed events
- [ ] **Phase 2.** MusicBrainz matching (tracklist completeness, cover art), auto-tagging,
      `Artist/Album` folder layout, a wishlist that retries missing albums
- [ ] Assist sentences ("download OK Computer by Radiohead")

## Legal

HA Music Manager is a client for a peer-to-peer network. Download and share only content you
have the right to. The authors do not condone copyright infringement.

## License

[MIT](LICENSE) © Juan Manera
