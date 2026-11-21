from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
import yaml

from ha_music_manager.config import Settings, load_settings
from ha_music_manager.engine import SlskdEngine, slskd_config


def make_settings(tmp_path: Path, **extra: object) -> Settings:
    return Settings.model_validate(
        {
            "soulseek_username": "juan",
            "soulseek_password": "hunter2",
            "download_dir": tmp_path / "music",
            "incomplete_dir": tmp_path / "incomplete",
            "data_dir": tmp_path / "data",
            **extra,
        }
    )


def test_slskd_config_keeps_api_on_loopback(tmp_path: Path) -> None:
    config = slskd_config(make_settings(tmp_path, share_dirs=["/media/shared"]), "x" * 32)
    assert config["web"]["ip_address"] == "127.0.0.1"
    key = config["web"]["authentication"]["api_keys"]["ha_music_manager"]
    assert key["key"] == "x" * 32 and key["cidr"].startswith("127.0.0.1")
    assert config["soulseek"]["username"] == "juan"
    assert config["shares"]["directories"] == ["/media/shared"]


def test_write_config_creates_dirs_and_private_file(tmp_path: Path) -> None:
    engine = SlskdEngine(make_settings(tmp_path))
    path = engine.write_config()
    assert (tmp_path / "music").is_dir() and (tmp_path / "incomplete").is_dir()
    assert path.stat().st_mode & 0o777 == 0o600
    assert yaml.safe_load(path.read_text())["soulseek"]["password"] == "hunter2"
    assert len(engine.api_key) >= 16  # slskd's minimum


async def test_engine_restarts_a_crashing_slskd(tmp_path: Path) -> None:
    fake = tmp_path / "slskd"
    fake.write_text('#!/bin/sh\necho "starting with $SLSKD_CONFIG"\nexit 1\n')
    fake.chmod(0o755)
    engine = SlskdEngine(make_settings(tmp_path, slskd_binary=fake))
    engine.start()
    for _ in range(100):
        if engine.restarts:
            break
        await asyncio.sleep(0.02)
    await engine.stop()
    assert engine.restarts >= 1
    assert not engine.running


async def test_engine_stop_terminates_a_running_slskd(tmp_path: Path) -> None:
    fake = tmp_path / "slskd"
    fake.write_text("#!/bin/sh\nexec sleep 30\n")
    fake.chmod(0o755)
    engine = SlskdEngine(make_settings(tmp_path, slskd_binary=fake))
    engine.start()
    for _ in range(100):
        if engine.running:
            break
        await asyncio.sleep(0.02)
    assert engine.running
    await engine.stop()
    assert not engine.running


def test_load_settings_merges_options_file_and_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    options = tmp_path / "options.json"
    options.write_text(json.dumps({"soulseek_username": "juan", "log_level": "debug"}))
    monkeypatch.setenv("HMM_LOG_LEVEL", "warning")
    monkeypatch.setenv("HMM_SHARE_DIRS", '["/media/a"]')
    settings = load_settings(options)
    assert settings.soulseek_username == "juan"
    assert settings.log_level == "warning"
    assert settings.share_dirs == [Path("/media/a")]
    assert settings.manage_slskd
    assert not load_settings(tmp_path / "missing.json").soulseek_username
