# Changelog

## 0.2.1

- Show why Soulseek is not logged in (e.g. a rejected username or password) in the app header,
  the `error` attribute of the Soulseek connection sensor and the app log. slskd's warnings and
  errors used to be logged at debug level only.

## 0.2.0

- New Home Assistant integration (install from HACS), set up automatically through Supervisor
  discovery.
- Sensors: Soulseek connection, active albums, queued and downloading files, download speed,
  completed and failed albums.
- Actions: `music_manager.search` (returns the best albums) and `music_manager.download_best`.
- Events: `music_manager_download_completed` and `music_manager_download_failed`.
- The app accepts the integration's key besides Ingress. The key is created on first start
  and kept in `/data/integration_key`.

## 0.1.0

- First release: bundled slskd 0.26.2 engine, album-oriented Soulseek search with quality
  scoring, one-click album downloads with live progress, Ingress sidebar panel.
