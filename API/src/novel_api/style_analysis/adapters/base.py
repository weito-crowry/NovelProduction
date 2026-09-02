from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal, Protocol

from novel_core.errors import NovelMcpError
from novel_core.style_analysis.fingerprints import JsonObject

SourceType = Literal["text", "html_file", "epub"]


@dataclass(frozen=True, slots=True)
class SourceRequest:
    source_type: SourceType
    filename: str
    payload: bytes


@dataclass(frozen=True, slots=True)
class SourceIdentity:
    external_work_id: str


@dataclass(frozen=True, slots=True)
class ImportedEpisode:
    external_episode_id: str
    title: str
    order_index: int
    raw_text: str
    metadata: JsonObject


@dataclass(frozen=True, slots=True)
class ImportedWork:
    title: str
    author_name: str | None
    metadata: JsonObject
    episodes: tuple[ImportedEpisode, ...]


class SourceAdapter(Protocol):
    adapter_id: str
    adapter_version: int

    def identify(self, request: SourceRequest) -> SourceIdentity: ...

    def import_work(self, request: SourceRequest) -> ImportedWork: ...


class SourceImportError(ValueError, NovelMcpError):
    code = "SOURCE_PARSE_ERROR"

    def __init__(self, message: str = "source import failed") -> None:
        self.message = message
        super().__init__(f"{self.code}: {message}")


class SourceEncodingError(SourceImportError):
    code = "SOURCE_ENCODING_ERROR"


class SourceEmptyError(SourceImportError):
    code = "SOURCE_EMPTY"


class SourceTooLargeError(SourceImportError):
    code = "SOURCE_TOO_LARGE"


class SourceParseError(SourceImportError):
    code = "SOURCE_PARSE_ERROR"


class UnsupportedSourceTypeError(SourceImportError):
    code = "SOURCE_TYPE_UNSUPPORTED"

    def __init__(self, source_type: str) -> None:
        super().__init__(f"unsupported source type: {source_type}")


def upload_identity(payload: bytes) -> SourceIdentity:
    return SourceIdentity(hashlib.sha256(payload).hexdigest())
