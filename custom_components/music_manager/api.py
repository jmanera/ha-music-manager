"""Client for the Music Manager app's API, reached over the Supervisor network."""

from __future__ import annotations

import json
from typing import Any

import aiohttp


class MusicManagerError(Exception):
    """The app answered with an error."""


class MusicManagerConnectionError(MusicManagerError):
    """The app is not reachable."""


class MusicManagerAuthError(MusicManagerError):
    """The API key was rejected."""


class MusicManagerNotFoundError(MusicManagerError):
    """Nothing matched (no album for the query, unknown search)."""


class MusicManagerApi:
    def __init__(self, session: aiohttp.ClientSession, host: str, port: int, api_key: str) -> None:
        self._session = session
        self._base = f"http://{host}:{port}/api"
        self._headers = {"Authorization": f"Bearer {api_key}"}

    async def _request(
        self, method: str, path: str, payload: dict[str, Any] | None = None, seconds: float = 15
    ) -> Any:
        try:
            async with self._session.request(
                method,
                f"{self._base}/{path}",
                json=payload,
                headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=seconds),
            ) as response:
                if response.status in (401, 403):
                    raise MusicManagerAuthError("The app rejected the API key")
                text = await response.text()
                body = json.loads(text) if text else {}
                if response.status == 404:
                    raise MusicManagerNotFoundError(_detail(body, "Not found"))
                if response.status >= 400:
                    raise MusicManagerError(_detail(body, f"HTTP {response.status}"))
                return body
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise MusicManagerConnectionError(str(err) or type(err).__name__) from err

    async def overview(self) -> dict[str, Any]:
        result: dict[str, Any] = await self._request("GET", "overview")
        return result

    async def search(self, query: str, search_time: float, **filters: Any) -> dict[str, Any]:
        result: dict[str, Any] = await self._request(
            "POST",
            "search-and-wait",
            {"query": query, "timeout": search_time, **filters},
            seconds=search_time + 30,
        )
        return result

    async def download_best(self, query: str, search_time: float, **filters: Any) -> dict[str, Any]:
        result: dict[str, Any] = await self._request(
            "POST",
            "download-best",
            {"query": query, "timeout": search_time, **filters},
            seconds=search_time + 30,
        )
        return result


def _detail(body: Any, default: str) -> str:
    if isinstance(body, dict) and isinstance(body.get("detail"), str):
        return str(body["detail"])
    return default
