from __future__ import annotations

from pathlib import Path

from novel_api.style_analysis.adapters.base import (
    ImportedEpisode,
    ImportedWork,
    SourceAdapter,
    SourceEmptyError,
    SourceIdentity,
    SourceRequest,
    SourceTooLargeError,
    upload_identity,
)
from novel_api.style_analysis.adapters.html_dom import extract_html_document
from novel_api.style_analysis.adapters.text import MAX_EPISODE_CODE_POINTS


class HtmlFileSourceAdapter(SourceAdapter):
    adapter_id = "style-source-html-file"
    adapter_version = 1

    def identify(self, request: SourceRequest) -> SourceIdentity:
        return upload_identity(request.payload)

    def import_work(self, request: SourceRequest) -> ImportedWork:
        extraction = extract_html_document(request.payload)
        if not extraction.raw_text:
            raise SourceEmptyError("HTML source is empty")
        if len(extraction.raw_text) > MAX_EPISODE_CODE_POINTS:
            raise SourceTooLargeError("episode text is too large")
        title = extraction.title or Path(request.filename).stem or request.filename
        episode = ImportedEpisode(
            external_episode_id="1",
            title=title,
            order_index=1,
            raw_text=extraction.raw_text,
            metadata={
                "scene_break_offsets_raw": list(extraction.scene_break_offsets_raw)
            },
        )
        return ImportedWork(
            title=title,
            author_name=None,
            metadata={},
            episodes=(episode,),
        )
