"""Lets the Home Assistant integration find and authenticate to this app.

The integration reaches the app over the Supervisor's internal network, not through Ingress, so
it authenticates with a key. The app announces host, port and key through Supervisor discovery
and Home Assistant offers to set up the integration with them.
"""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
import socket
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

SERVICE = "music_manager"
SUPERVISOR_URL = "http://supervisor"


def integration_key(data_dir: Path) -> str:
    """The integration's API key, created on first start and kept across restarts."""
    path = data_dir / "integration_key"
    if path.is_file():
        key = path.read_text().strip()
        if len(key) >= 32:
            return key
    key = secrets.token_urlsafe(32)
    data_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(key)
    path.chmod(0o600)
    return key


async def announce(
    port: int,
    api_key: str,
    supervisor_url: str = SUPERVISOR_URL,
    attempts: int = 5,
    retry_delay: float = 10.0,
) -> bool:
    """Tell the Supervisor how to reach us. No-op outside Home Assistant."""
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        log.info("Not running under the Supervisor; skipping discovery")
        return False
    # The Supervisor names the container after the app, and HA Core resolves that name.
    payload = {
        "service": SERVICE,
        "config": {"host": socket.gethostname(), "port": port, "api_key": api_key},
    }
    async with httpx.AsyncClient(
        base_url=supervisor_url, headers={"Authorization": f"Bearer {token}"}, timeout=10
    ) as http:
        for attempt in range(1, attempts + 1):
            try:
                response = await http.post("/discovery", json=payload)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                log.warning("Discovery attempt %d/%d failed: %s", attempt, attempts, exc)
                await asyncio.sleep(retry_delay)
                continue
            log.info("Announced to Home Assistant through Supervisor discovery")
            return True
    return False
