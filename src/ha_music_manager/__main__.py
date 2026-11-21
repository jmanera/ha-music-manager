"""Entry point: `ha-music-manager` / `python -m ha_music_manager`."""

from __future__ import annotations

import logging

import uvicorn

from ha_music_manager.api import create_app
from ha_music_manager.config import load_settings


def main() -> None:
    settings = load_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    uvicorn.run(
        create_app(settings),
        host="0.0.0.0",  # noqa: S104  # nosec B104 - the app only answers the Ingress gateway
        port=settings.http_port,
        log_level=settings.log_level,
        proxy_headers=False,
    )


if __name__ == "__main__":
    main()
