"""App settings, read from the Supervisor's options file (or environment overrides in dev)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

OPTIONS_FILE = Path("/data/options.json")


class Settings(BaseModel):
    soulseek_username: str = ""
    soulseek_password: str = ""
    download_dir: Path = Path("/media/music")
    incomplete_dir: Path = Path("/share/ha-music-manager/incomplete")
    share_dirs: list[Path] = Field(default_factory=list)
    log_level: Literal["debug", "info", "warning", "error"] = "info"

    # Not user options: where slskd lives and how we reach it.
    data_dir: Path = Path("/data")
    slskd_binary: Path = Path("/opt/slskd/slskd")
    slskd_port: int = 5030
    soulseek_listen_port: int = 50300
    http_port: int = 8099
    ingress_only: bool = False  # the image sets it: answer only the Ingress gateway
    # Dev mode: talk to an slskd you started yourself instead of spawning one.
    slskd_url: str | None = None
    slskd_api_key: str | None = None

    @property
    def manage_slskd(self) -> bool:
        return self.slskd_url is None


def load_settings(options_file: Path = OPTIONS_FILE) -> Settings:
    """Merge the Supervisor options file with `HMM_*` environment variables (env wins)."""
    raw: dict[str, object] = {}
    if options_file.is_file():
        raw.update(json.loads(options_file.read_text()))
    for field in Settings.model_fields:
        value = os.environ.get(f"HMM_{field.upper()}")
        if value is not None:
            raw[field] = json.loads(value) if field == "share_dirs" else value
    return Settings.model_validate(raw)
