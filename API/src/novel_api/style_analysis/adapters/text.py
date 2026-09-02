from __future__ import annotations

from pathlib import Path

from novel_api.style_analysis.adapters.base import (
    ImportedEpisode,
    ImportedWork,
    SourceAdapter,
    SourceEmptyError,
    SourceEncodingError,
    SourceIdentity,
    SourceRequest,
    SourceTooLargeError,
    upload_identity,
)

MAX_EPISODE_CODE_POINTS = 2_000_000


class TextSourceAdapter(SourceAdapter):
    adapter_id = "style-source-text"
    adapter_version = 1

    def identify(self, request: SourceRequest) -> SourceIdentity:
        return upload_identity(request.payload)

    def import_work(self, request: SourceRequest) -> ImportedWork:
        try:
            raw_text = request.payload.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise SourceEncodingError("text source is not valid UTF-8") from exc
        if not raw_text:
            raise SourceEmptyError("text source is empty")
        if len(raw_text) > MAX_EPISODE_CODE_POINTS:
            raise SourceTooLargeError("episode text is too large")
        title = Path(request.filename).stem or request.filename or "untitled"
        episode = ImportedEpisode(
            external_episode_id="1",
            title=title,
            order_index=1,
            raw_text=raw_text,
            metadata={"scene_break_offsets_raw": []},
        )
        return ImportedWork(
            title=title,
            author_name=None,
            metadata={},
            episodes=(episode,),
        )
