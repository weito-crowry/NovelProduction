from __future__ import annotations

import io
import posixpath
import zipfile
from pathlib import Path
from typing import cast
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from novel_api.style_analysis.adapters.base import (
    ImportedEpisode,
    ImportedWork,
    SourceAdapter,
    SourceEmptyError,
    SourceIdentity,
    SourceParseError,
    SourceRequest,
    SourceTooLargeError,
    upload_identity,
)
from novel_api.style_analysis.adapters.html_dom import extract_html_document
from novel_api.style_analysis.adapters.text import MAX_EPISODE_CODE_POINTS

_MAX_SELECTED_UNCOMPRESSED_BYTES = 200 * 1024 * 1024
_XHTML_MEDIA_TYPES = frozenset(
    {"application/xhtml+xml", "application/xml", "text/html"}
)


def _local_name(element: ElementTree.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _children_by_name(
    element: ElementTree.Element, name: str
) -> tuple[ElementTree.Element, ...]:
    return tuple(child for child in element.iter() if _local_name(child) == name)


class EpubSourceAdapter(SourceAdapter):
    adapter_id = "style-source-epub"
    adapter_version = 1

    def identify(self, request: SourceRequest) -> SourceIdentity:
        return upload_identity(request.payload)

    def import_work(self, request: SourceRequest) -> ImportedWork:
        try:
            archive = zipfile.ZipFile(io.BytesIO(request.payload))
        except (OSError, zipfile.BadZipFile) as exc:
            raise SourceParseError("EPUB archive is invalid") from exc
        with archive:
            container = _read_xml(archive, "META-INF/container.xml")
            rootfiles = _children_by_name(container, "rootfile")
            if not rootfiles:
                raise SourceParseError("EPUB rootfile is missing")
            opf_path = rootfiles[0].get("full-path")
            if not opf_path:
                raise SourceParseError("EPUB OPF path is missing")
            opf_path = _resolve_archive_path("", opf_path)
            package = _read_xml(archive, opf_path)
            opf_dir = posixpath.dirname(opf_path)
            manifest = _manifest(package)
            spine, toc_id = _spine(package)
            selected = []
            for itemref in spine:
                if itemref not in manifest:
                    raise SourceParseError("EPUB spine item is missing from manifest")
                item = manifest[itemref]
                if _is_episode_item(item):
                    selected.append(item)
            if not selected:
                raise SourceEmptyError("EPUB has no readable spine episodes")
            total_size = 0
            for item in selected:
                path = _resolve_archive_path(opf_dir, item["href"])
                try:
                    total_size += archive.getinfo(path).file_size
                except KeyError as exc:
                    raise SourceParseError("EPUB spine resource is missing") from exc
            if total_size > _MAX_SELECTED_UNCOMPRESSED_BYTES:
                raise SourceTooLargeError("EPUB spine resources are too large")

            labels = _navigation_labels(archive, opf_dir, manifest, package, toc_id)
            episodes: list[ImportedEpisode] = []
            for order_index, item in enumerate(selected, start=1):
                path = _resolve_archive_path(opf_dir, item["href"])
                try:
                    payload = archive.read(path)
                except (KeyError, OSError, zipfile.BadZipFile) as exc:
                    raise SourceParseError(
                        "EPUB spine resource cannot be read"
                    ) from exc
                extraction = extract_html_document(payload)
                if not extraction.raw_text:
                    raise SourceEmptyError("EPUB episode is empty")
                if len(extraction.raw_text) > MAX_EPISODE_CODE_POINTS:
                    raise SourceTooLargeError("episode text is too large")
                label = labels.get(path)
                title = label or _first_heading(payload) or f"Episode {order_index}"
                episodes.append(
                    ImportedEpisode(
                        external_episode_id=f"spine:{order_index}",
                        title=title,
                        order_index=order_index,
                        raw_text=extraction.raw_text,
                        metadata={
                            "scene_break_offsets_raw": list(
                                extraction.scene_break_offsets_raw
                            )
                        },
                    )
                )

            title = _metadata_value(package, "title") or Path(request.filename).stem
            author = _metadata_value(package, "creator")
            return ImportedWork(
                title=title or request.filename or "untitled",
                author_name=author,
                metadata={},
                episodes=tuple(episodes),
            )


def _read_xml(archive: zipfile.ZipFile, path: str) -> ElementTree.Element:
    try:
        payload = archive.read(path)
        return ElementTree.fromstring(payload)
    except (KeyError, OSError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise SourceParseError(f"EPUB XML resource is invalid: {path}") from exc


def _resolve_archive_path(base_dir: str, href: str) -> str:
    if "\\" in href:
        raise SourceParseError("EPUB resource path is not POSIX")
    path = posixpath.normpath(posixpath.join(base_dir, href.split("#", 1)[0]))
    if (
        not path
        or path == "."
        or path.startswith("../")
        or path == ".."
        or path.startswith("/")
    ):
        raise SourceParseError("EPUB resource path escapes archive root")
    return path


def _manifest(package: ElementTree.Element) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for item in _children_by_name(package, "item"):
        item_id = item.get("id")
        href = item.get("href")
        media_type = item.get("media-type")
        if item_id and href and media_type:
            result[item_id] = {
                "href": href,
                "media_type": media_type,
                "properties": item.get("properties", ""),
            }
    return result


def _spine(package: ElementTree.Element) -> tuple[tuple[str, ...], str | None]:
    spine_nodes = _children_by_name(package, "spine")
    if not spine_nodes:
        raise SourceParseError("EPUB spine is missing")
    spine = spine_nodes[0]
    itemrefs = tuple(
        itemref.get("idref")
        for itemref in spine
        if _local_name(itemref) == "itemref" and itemref.get("idref")
    )
    return cast(tuple[str, ...], itemrefs), spine.get("toc")


def _is_episode_item(item: dict[str, str]) -> bool:
    properties = set(item["properties"].split())
    return item["media_type"] in _XHTML_MEDIA_TYPES and not (
        "nav" in properties
        or "cover-image" in properties
        or "cover" in item["href"].lower()
    )


def _metadata_value(package: ElementTree.Element, name: str) -> str | None:
    for element in _children_by_name(package, name):
        value = "".join(element.itertext()).strip()
        if value:
            return value
    return None


def _navigation_labels(
    archive: zipfile.ZipFile,
    opf_dir: str,
    manifest: dict[str, dict[str, str]],
    package: ElementTree.Element,
    toc_id: str | None,
) -> dict[str, str]:
    labels: dict[str, str] = {}
    nav_item = next(
        (
            item
            for item in manifest.values()
            if "nav" in set(item["properties"].split())
        ),
        None,
    )
    if nav_item is not None:
        nav_path = _resolve_navigation_path(opf_dir, nav_item["href"])
        if nav_path is None:
            return labels
        try:
            payload = archive.read(nav_path)
        except (KeyError, OSError, zipfile.BadZipFile):
            return labels
        soup = BeautifulSoup(payload, "html.parser")
        for anchor in soup.find_all("a"):
            href = anchor.get("href")
            label = anchor.get_text(" ", strip=True)
            if isinstance(href, str) and label:
                target_path = _resolve_navigation_path(
                    posixpath.dirname(nav_path), href
                )
                if target_path is not None:
                    labels[target_path] = label
        return labels

    if toc_id is None or toc_id not in manifest:
        return labels
    ncx_item = manifest[toc_id]
    ncx_path = _resolve_navigation_path(opf_dir, ncx_item["href"])
    if ncx_path is None:
        return labels
    try:
        ncx = _read_xml(archive, ncx_path)
    except SourceParseError:
        return labels
    for nav_point in _children_by_name(ncx, "navPoint"):
        content = next(
            (child for child in nav_point if _local_name(child) == "content"), None
        )
        if content is None or not content.get("src"):
            continue
        label_element = next(
            (child for child in nav_point if _local_name(child) == "navLabel"), None
        )
        if label_element is None:
            continue
        label = "".join(label_element.itertext()).strip()
        content_src = content.get("src")
        if label and isinstance(content_src, str):
            target_path = _resolve_navigation_path(
                posixpath.dirname(ncx_path), content_src
            )
            if target_path is not None:
                labels[target_path] = label
    return labels


def _resolve_navigation_path(base_dir: str, href: str) -> str | None:
    try:
        return _resolve_archive_path(base_dir, href)
    except SourceParseError:
        return None


def _first_heading(payload: bytes) -> str | None:
    soup = BeautifulSoup(payload, "html.parser")
    for name in ("h1", "h2", "h3", "h4", "h5", "h6"):
        heading = soup.find(name)
        if heading is not None:
            value = heading.get_text(" ", strip=True)
            if value:
                return value
    return None
