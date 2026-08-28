from __future__ import annotations

import json
from typing import Any, NoReturn

from novel_api.errors import ApiVersionConflictError, build_conflict_details
from novel_api.schemas.common import ProjectEnvelope
from novel_api.serialization import serialize_value


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def envelope(project_id: str, value: Any) -> ProjectEnvelope[Any]:
    return ProjectEnvelope(project_id=project_id, data=serialize_value(value))


def raise_version_conflict(
    *,
    entity_type: str,
    entity_id: int | str,
    expected_version: int,
    current_resource: Any,
) -> NoReturn:
    current_version = current_resource.version
    if not isinstance(current_version, int):
        raise TypeError("current resource version must be an integer")
    raise ApiVersionConflictError(
        build_conflict_details(
            entity_type=entity_type,
            entity_id=entity_id,
            expected_version=expected_version,
            current_version=current_version,
            current_resource=current_resource,
        )
    )
