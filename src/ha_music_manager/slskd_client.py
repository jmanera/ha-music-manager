"""Async client for the slskd REST API (v0)."""

from __future__ import annotations

import uuid
from typing import Any
from urllib.parse import quote

import httpx

from ha_music_manager.slskd_models import (
    Search,
    SearchResponse,
    ServerState,
    UserTransfers,
)


class SlskdUnavailableError(Exception):
    """slskd is not running yet, or not answering."""


class SlskdClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 15.0) -> None:
        self._http = httpx.AsyncClient(
            base_url=f"{base_url.rstrip('/')}/api/v0",
            headers={"X-API-Key": api_key},
            timeout=timeout,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = await self._http.request(method, path, **kwargs)
        except httpx.TransportError as exc:
            raise SlskdUnavailableError(str(exc)) from exc
        response.raise_for_status()
        return response.json() if response.content else None

    async def server_state(self) -> ServerState:
        # /server needs an administrator key; /application embeds the same state for readwrite.
        data = await self._request("GET", "/application")
        return ServerState.model_validate(data["server"])

    async def start_search(self, text: str, timeout_ms: int = 15_000) -> Search:
        body = {
            "id": str(uuid.uuid4()),
            "searchText": text,
            "searchTimeout": timeout_ms,
            "filterResponses": True,
            "responseLimit": 200,
            "fileLimit": 20_000,
        }
        return Search.model_validate(await self._request("POST", "/searches", json=body))

    async def get_search(self, search_id: str) -> Search:
        return Search.model_validate(await self._request("GET", f"/searches/{search_id}"))

    async def get_responses(self, search_id: str) -> list[SearchResponse]:
        data = await self._request("GET", f"/searches/{search_id}/responses")
        return [SearchResponse.model_validate(r) for r in data]

    async def delete_search(self, search_id: str) -> None:
        await self._request("DELETE", f"/searches/{search_id}")

    async def enqueue(self, username: str, files: list[tuple[str, int]]) -> None:
        body = [{"filename": name, "size": size} for name, size in files]
        await self._request("POST", f"/transfers/downloads/{quote(username, safe='')}", json=body)

    async def downloads(self) -> list[UserTransfers]:
        data = await self._request("GET", "/transfers/downloads")
        return [UserTransfers.model_validate(u) for u in data]

    async def cancel_download(self, username: str, transfer_id: str, remove: bool) -> None:
        await self._request(
            "DELETE",
            f"/transfers/downloads/{quote(username, safe='')}/{transfer_id}",
            params={"remove": str(remove).lower()},
        )

    async def clear_completed(self) -> None:
        await self._request("DELETE", "/transfers/downloads/all/completed")
