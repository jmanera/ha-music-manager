"""HTTP API for the web UI, plus the built UI itself. Served to Home Assistant through Ingress.

Every URL in the UI is relative, so it works under Ingress' `/api/hassio_ingress/<token>/` prefix
without knowing it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ha_music_manager import __version__
from ha_music_manager.albums import AlbumCandidate, group_albums, split_path
from ha_music_manager.config import Settings
from ha_music_manager.engine import SlskdEngine
from ha_music_manager.slskd_client import SlskdClient, SlskdUnavailableError

STATIC_DIR = Path(__file__).parent / "static"
INGRESS_PROXY = "172.30.32.2"  # the Supervisor's Ingress gateway


class Status(BaseModel):
    version: str
    engine: Literal["managed", "external"]
    connected: bool
    logged_in: bool
    server_state: str
    username: str


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=200)


class SearchStarted(BaseModel):
    id: str


class SearchResult(BaseModel):
    id: str
    query: str
    complete: bool
    response_count: int
    albums: list[AlbumCandidate]


class FileRef(BaseModel):
    filename: str
    size: int


class DownloadRequest(BaseModel):
    username: str
    files: list[FileRef] = Field(min_length=1)


class DownloadFile(BaseModel):
    id: str
    name: str
    state: str
    size: int
    percent: float
    speed: float
    error: str | None


class DownloadGroup(BaseModel):
    username: str
    directory: str
    title: str
    percent: float
    state: Literal["queued", "downloading", "completed", "failed"]
    files: list[DownloadFile]


def group_state(states: list[str]) -> Literal["queued", "downloading", "completed", "failed"]:
    """slskd states look like "Queued, Remotely", "InProgress", "Completed, Succeeded"."""
    if any(s.startswith("InProgress") or s.startswith("Initializing") for s in states):
        return "downloading"
    if all(s.startswith("Completed") for s in states):
        succeeded = all(s.endswith("Succeeded") for s in states)
        return "completed" if succeeded else "failed"
    return "queued"


def create_app(settings: Settings, client: SlskdClient | None = None) -> FastAPI:
    engine = SlskdEngine(settings) if settings.manage_slskd and client is None else None

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        nonlocal client
        if engine:
            engine.start()
            client = SlskdClient(engine.base_url, engine.api_key)
        elif client is None:
            client = SlskdClient(settings.slskd_url or "", settings.slskd_api_key or "")
        app.state.client = client
        yield
        await client.aclose()
        if engine:
            await engine.stop()

    app = FastAPI(title="HA Music Manager", version=__version__, lifespan=lifespan)
    if client is not None:
        app.state.client = client

    if settings.ingress_only:

        @app.middleware("http")
        async def only_ingress(
            request: Request, call_next: Callable[[Request], Awaitable[Response]]
        ) -> Response:
            if request.client is None or request.client.host not in (INGRESS_PROXY, "127.0.0.1"):
                return JSONResponse({"detail": "Use Home Assistant to open this app"}, 403)
            return await call_next(request)

    def slskd(request: Request) -> SlskdClient:
        c: SlskdClient = request.app.state.client
        return c

    @app.exception_handler(SlskdUnavailableError)
    async def unavailable(_: Request, exc: SlskdUnavailableError) -> JSONResponse:
        return JSONResponse({"detail": "The Soulseek engine is starting"}, status_code=503)

    @app.exception_handler(httpx.HTTPStatusError)
    async def upstream_error(_: Request, exc: httpx.HTTPStatusError) -> JSONResponse:
        # 404 (unknown search) and 409 (not logged in to Soulseek) carry a useful message.
        code = exc.response.status_code
        if code in (404, 409):
            detail = exc.response.text.strip().strip('"') or f"slskd answered {code}"
            return JSONResponse({"detail": detail[:300]}, status_code=code)
        return JSONResponse({"detail": f"slskd answered {code}"}, status_code=502)

    @app.get("/api/status")
    async def status(request: Request) -> Status:
        state = await slskd(request).server_state()
        return Status(
            version=__version__,
            engine="external" if engine is None else "managed",
            connected=state.is_connected,
            logged_in=state.is_logged_in,
            server_state=state.state,
            username=settings.soulseek_username,
        )

    @app.post("/api/searches", status_code=201)
    async def start_search(body: SearchRequest, request: Request) -> SearchStarted:
        search = await slskd(request).start_search(body.query.strip())
        return SearchStarted(id=search.id)

    @app.get("/api/searches/{search_id}")
    async def get_search(search_id: str, request: Request) -> SearchResult:
        c = slskd(request)
        search = await c.get_search(search_id)
        responses = await c.get_responses(search_id)
        return SearchResult(
            id=search.id,
            query=search.search_text,
            complete=search.is_complete,
            response_count=search.response_count,
            albums=group_albums(responses),
        )

    @app.delete("/api/searches/{search_id}", status_code=204)
    async def delete_search(search_id: str, request: Request) -> None:
        await slskd(request).delete_search(search_id)

    @app.post("/api/downloads", status_code=202)
    async def download(body: DownloadRequest, request: Request) -> None:
        await slskd(request).enqueue(body.username, [(f.filename, f.size) for f in body.files])

    @app.get("/api/downloads")
    async def downloads(request: Request) -> list[DownloadGroup]:
        groups: list[DownloadGroup] = []
        for user in await slskd(request).downloads():
            for directory in user.directories:
                if not directory.files:
                    continue
                total = sum(f.size for f in directory.files) or 1
                done = sum(f.bytes_transferred for f in directory.files)
                groups.append(
                    DownloadGroup(
                        username=user.username,
                        directory=directory.directory,
                        title=directory.directory.replace("/", "\\").rpartition("\\")[2],
                        percent=round(100 * done / total, 1),
                        state=group_state([f.state for f in directory.files]),
                        files=[
                            DownloadFile(
                                id=f.id,
                                name=split_path(f.filename)[1],
                                state=f.state,
                                size=f.size,
                                percent=round(f.percent_complete, 1),
                                speed=f.average_speed,
                                error=f.exception,
                            )
                            for f in directory.files
                        ],
                    )
                )
        return groups

    @app.delete("/api/downloads/completed", status_code=204)
    async def clear_completed(request: Request) -> None:
        await slskd(request).clear_completed()

    @app.delete("/api/downloads/{username}/{transfer_id}", status_code=204)
    async def cancel(username: str, transfer_id: str, request: Request) -> None:
        await slskd(request).cancel_download(username, transfer_id, remove=True)

    @app.get("/api/{path:path}", include_in_schema=False)
    async def api_not_found(path: str) -> None:
        raise HTTPException(404)

    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="ui")
    return app
