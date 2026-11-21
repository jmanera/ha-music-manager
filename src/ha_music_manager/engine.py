"""Runs slskd as a child process: writes its config, starts it and restarts it if it dies."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
import secrets
from pathlib import Path
from typing import Any

import yaml

from ha_music_manager.config import Settings

log = logging.getLogger(__name__)

# slskd's console lines look like "[18:38:25 WRN] Failed to log in: ...". Stack traces and other
# continuation lines carry no prefix.
SLSKD_LINE = re.compile(r"^\[\d{2}:\d{2}:\d{2} (?P<level>[A-Z]{3})\] (?P<message>.*)$")
SLSKD_LEVELS = {"WRN": logging.WARNING, "ERR": logging.ERROR, "FTL": logging.CRITICAL}


def slskd_config(settings: Settings, api_key: str) -> dict[str, Any]:
    """slskd.yml contents. The web API listens on loopback only and needs our API key."""
    return {
        "headless": True,  # we bring our own UI; the API stays on
        "flags": {"no_logo": True, "no_version_check": True},
        "directories": {
            "downloads": str(settings.download_dir),
            "incomplete": str(settings.incomplete_dir),
        },
        "shares": {"directories": [str(d) for d in settings.share_dirs]},
        "web": {
            "port": settings.slskd_port,
            "ip_address": "127.0.0.1",
            "https": {"disabled": True},
            "authentication": {
                "disabled": False,
                "api_keys": {
                    "ha_music_manager": {
                        "key": api_key,
                        "role": "readwrite",
                        "cidr": "127.0.0.1/32,::1/128",
                    }
                },
            },
        },
        "soulseek": {
            "username": settings.soulseek_username,
            "password": settings.soulseek_password,
            "listen_port": settings.soulseek_listen_port,
        },
    }


class SlskdEngine:
    """Supervises the slskd process for the lifetime of the app."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.api_key = secrets.token_urlsafe(32)
        self.app_dir = settings.data_dir / "slskd"
        self._task: asyncio.Task[None] | None = None
        self._process: asyncio.subprocess.Process | None = None
        self.restarts = 0
        self.last_error: str | None = None  # last slskd warning or error, e.g. a rejected login

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.settings.slskd_port}"

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    def write_config(self) -> Path:
        self.app_dir.mkdir(parents=True, exist_ok=True)
        for directory in (self.settings.download_dir, self.settings.incomplete_dir):
            directory.mkdir(parents=True, exist_ok=True)
        path = self.app_dir / "slskd.yml"
        path.write_text(yaml.safe_dump(slskd_config(self.settings, self.api_key)))
        path.chmod(0o600)  # contains the Soulseek password
        return path

    def start(self) -> None:
        config = self.write_config()
        self._task = asyncio.create_task(self._supervise(config))

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        if self.running and self._process:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=10)
            except TimeoutError:
                self._process.kill()

    def _relay(self, line: str) -> None:
        """Pass slskd's output on, surfacing warnings and errors at the app's default log level."""
        match = SLSKD_LINE.match(line)
        level = SLSKD_LEVELS.get(match["level"], logging.DEBUG) if match else logging.DEBUG
        if match and level > logging.DEBUG:
            self.last_error = match["message"][:300]
        log.log(level, "slskd: %s", line)

    async def _supervise(self, config: Path) -> None:
        env = {
            **os.environ,
            "SLSKD_APP_DIR": str(self.app_dir),
            "SLSKD_CONFIG": str(config),
            "DOTNET_SYSTEM_GLOBALIZATION_INVARIANT": "1",
        }
        backoff = 1.0
        while True:
            log.info("Starting slskd")
            self._process = await asyncio.create_subprocess_exec(
                str(self.settings.slskd_binary),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            if self._process.stdout:  # always set: stdout=PIPE
                async for line in self._process.stdout:
                    self._relay(line.decode(errors="replace").rstrip())
            code = await self._process.wait()
            self.restarts += 1
            log.warning("slskd exited with code %s; restarting in %.0fs", code, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)
