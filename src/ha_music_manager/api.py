"""HTTP API for the web UI and the Home Assistant integration, plus the built UI itself.

The UI is served through Ingress. Every URL in it is relative, so it works under Ingress'
`/api/hassio_ingress/<token>/` prefix without knowing it. The integration talks to the app
directly over the Supervisor's network with a bearer key (see discovery.py).
"""

from __future__ import annotations

import asyncio
import contextlib
import secrets
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ha_music_manager import __version__, discovery
from ha_music_manager.albums import AlbumCandidate, AlbumSummary, group_albums
from ha_music_manager.config import Settings
from ha_music_manager.downloads import DownloadGroup, DownloadStats, build_groups, stats
from ha_music_manager.engine import SlskdEngine
from ha_music_manager.search import AlbumFilters, download_album, filter_albums, run_search
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


class DownloadSummary(BaseModel):
    username: str
    directory: str
    title: str
    state: str
    percent: float
    file_count: int


class Overview(BaseModel):
    """Everything the integration polls, in one request."""

    status: Status
    stats: DownloadStats
    downloads: list[DownloadSummary]


class AutoSearchRequest(AlbumFilters):
    query: str = Field(min_length=2, max_length=200)
    timeout: float = Field(default=20, ge=5, le=120)  # seconds
    limit: int = Field(default=10, ge=1, le=50)


class AutoSearchResult(BaseModel):
    query: str
    response_count: int
    albums: list[AlbumSummary]


class AutoDownloadResult(BaseModel):
    query: str
    album: AlbumSummary


def create_app(settings: Settings, client: SlskdClient | None = None) -> FastAPI:
    engine = SlskdEngine(settings) if settings.manage_slskd and client is None else None
    api_key = discovery.integration_key(settings.data_dir) if settings.ingress_only else None

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        nonlocal client
        if engine:
            engine.start()
            client = SlskdClient(engine.base_url, engine.api_key)
        elif client is None:
            client = SlskdClient(settings.slskd_url or "", settings.slskd_api_key or "")
        app.state.client = client
        announcing = (
            asyncio.create_task(discovery.announce(settings.http_port, api_key))
            if api_key
            else None
        )
        yield
        if announcing:
            announcing.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await announcing
        await client.aclose()
        if engine:
            await engine.stop()

    app = FastAPI(title="HA Music Manager", version=__version__, lifespan=lifespan)
    if client is not None:
        app.state.client = client

    if api_key:
        expected = f"Bearer {api_key}"

        @app.middleware("http")
        async def ingress_or_key(
            request: Request, call_next: Callable[[Request], Awaitable[Response]]
        ) -> Response:
            via_ingress = request.client is not None and request.client.host in (
                INGRESS_PROXY,
                "127.0.0.1",
            )
            given = request.headers.get("authorization", "")
            if not via_ingress and not secrets.compare_digest(given, expected):
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

    async def get_status(c: SlskdClient) -> Status:
        state = await c.server_state()
        return Status(
            version=__version__,
            engine="external" if engine is None else "managed",
            connected=state.is_connected,
            logged_in=state.is_logged_in,
            server_state=state.state,
            username=settings.soulseek_username,
        )

    @app.get("/api/status")
    async def status(request: Request) -> Status:
        return await get_status(slskd(request))

    @app.get("/api/overview")
    async def overview(request: Request) -> Overview:
        c = slskd(request)
        groups = build_groups(await c.downloads())
        return Overview(
            status=await get_status(c),
            stats=stats(groups),
            downloads=[
                DownloadSummary(
                    username=g.username,
                    directory=g.directory,
                    title=g.title,
                    state=g.state,
                    percent=g.percent,
                    file_count=len(g.files),
                )
                for g in groups
            ],
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

    @app.post("/api/search-and-wait")
    async def search_and_wait(body: AutoSearchRequest, request: Request) -> AutoSearchResult:
        query = body.query.strip()
        response_count, albums = await run_search(slskd(request), query, body.timeout)
        return AutoSearchResult(
            query=query,
            response_count=response_count,
            albums=[a.summary() for a in filter_albums(albums, body)[: body.limit]],
        )

    @app.post("/api/download-best", status_code=202)
    async def download_best(body: AutoSearchRequest, request: Request) -> AutoDownloadResult:
        c = slskd(request)
        query = body.query.strip()
        _, albums = await run_search(c, query, body.timeout)
        candidates = filter_albums(albums, body)
        if not candidates:
            raise HTTPException(404, f"No album matched {query!r} with these filters")
        await download_album(c, candidates[0])
        return AutoDownloadResult(query=query, album=candidates[0].summary())

    @app.post("/api/downloads", status_code=202)
    async def download(body: DownloadRequest, request: Request) -> None:
        await slskd(request).enqueue(body.username, [(f.filename, f.size) for f in body.files])

    @app.get("/api/downloads")
    async def downloads(request: Request) -> list[DownloadGroup]:
        return build_groups(await slskd(request).downloads())

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
