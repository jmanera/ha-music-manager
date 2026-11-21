from __future__ import annotations

from typing import Any


def search_file(filename: str, size: int = 30_000_000, **extra: Any) -> dict[str, Any]:
    """A file as slskd returns it in /searches/{id}/responses."""
    ext = filename.rpartition(".")[2]
    return {"filename": filename, "size": size, "extension": ext, **extra}


def search_response(username: str, files: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    return {
        "username": username,
        "files": files,
        "hasFreeUploadSlot": True,
        "queueLength": 0,
        "uploadSpeed": 2_000_000,
        **extra,
    }
