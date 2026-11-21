"""Constants for the Music Manager integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "music_manager"
DEFAULT_PORT: Final = 8099
SCAN_INTERVAL: Final = timedelta(seconds=10)

EVENT_DOWNLOAD_COMPLETED: Final = f"{DOMAIN}_download_completed"
EVENT_DOWNLOAD_FAILED: Final = f"{DOMAIN}_download_failed"

SERVICE_SEARCH: Final = "search"
SERVICE_DOWNLOAD_BEST: Final = "download_best"

ATTR_QUERY: Final = "query"
ATTR_LIMIT: Final = "limit"
ATTR_LOSSLESS_ONLY: Final = "lossless_only"
ATTR_FREE_SLOT_ONLY: Final = "free_slot_only"
ATTR_MIN_TRACKS: Final = "min_tracks"
ATTR_SEARCH_TIME: Final = "search_time"
