"""The subset of slskd's REST API (v0) payloads we use. slskd speaks camelCase JSON."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class _SlskdModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")


class SearchFile(_SlskdModel):
    filename: str
    size: int
    extension: str = ""
    bit_rate: int | None = None
    bit_depth: int | None = None
    sample_rate: int | None = None
    length: int | None = None  # seconds
    is_locked: bool = False


class SearchResponse(_SlskdModel):
    username: str
    files: list[SearchFile] = []
    locked_files: list[SearchFile] = []
    has_free_upload_slot: bool = False
    queue_length: int = 0
    upload_speed: int = 0  # bytes/s


class Search(_SlskdModel):
    id: str
    search_text: str
    state: str
    is_complete: bool = False
    response_count: int = 0
    file_count: int = 0


class Transfer(_SlskdModel):
    id: str
    username: str
    filename: str
    size: int
    state: str
    bytes_transferred: int = 0
    average_speed: float = 0.0
    percent_complete: float = 0.0
    exception: str | None = None


class TransferDirectory(_SlskdModel):
    directory: str
    files: list[Transfer] = []


class UserTransfers(_SlskdModel):
    username: str
    directories: list[TransferDirectory] = []


class ServerState(_SlskdModel):
    state: str = "Disconnected"
    is_connected: bool = False
    is_logged_in: bool = False
