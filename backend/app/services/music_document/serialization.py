"""MusicDocument (de)serialisation, version migration and error recovery.

Owner: pocket-music-core skill.  Reading a document must either produce a
complete valid document or raise a typed error - never a half-parsed object.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from pydantic import ValidationError

from app.core.errors import AppError, ValidationAppError
from app.core.logging import get_logger
from app.schemas.music_document import CURRENT_SCHEMA_VERSION, MusicDocument

logger = get_logger("pocketscore.document.serialization")

SUPPORTED_VERSIONS = {0, 1}


class DocumentVersionError(AppError):
    status_code = 422
    code = "DOCUMENT_VERSION_UNSUPPORTED"
    message = "Unsupported MusicDocument schema version"


def _migrate_v0_to_v1(data: Dict[str, Any]) -> Dict[str, Any]:
    """v0 used ``time``/``length`` and had no explicit rest kind."""
    events = []
    for raw in data.get("events", []) or []:
        event = dict(raw)
        if "start_time" not in event and "time" in event:
            event["start_time"] = event.pop("time")
        if "duration" not in event and "length" in event:
            event["duration"] = event.pop("length")
        event.setdefault("kind", "note" if event.get("pitch") is not None else "rest")
        event.setdefault("velocity", 96)
        event.setdefault("measure", 1)
        event.setdefault("beat", 1.0)
        events.append(event)
    migrated = dict(data)
    migrated["events"] = events
    migrated.setdefault("tracks", [{"track_id": "t1", "name": "主旋律"}])
    migrated["schema_version"] = 1
    logger.info("migrated MusicDocument from schema v0 to v1 (%d events)", len(events))
    return migrated


_MIGRATIONS = {0: _migrate_v0_to_v1}


def migrate(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Apply every migration needed to reach ``CURRENT_SCHEMA_VERSION``."""
    version = payload.get("schema_version")
    if version is None:
        # Documents written before schema_version existed are v0.
        version = 0
        payload = {**payload, "schema_version": 0}
    try:
        version = int(version)
    except (TypeError, ValueError) as exc:
        raise DocumentVersionError(
            f"invalid schema_version {version!r}",
            details={"supported": sorted(SUPPORTED_VERSIONS)},
        ) from exc

    if version not in SUPPORTED_VERSIONS:
        raise DocumentVersionError(
            f"schema_version {version} is not supported by this build",
            details={"received": version, "supported": sorted(SUPPORTED_VERSIONS)},
        )

    current = payload
    while version < CURRENT_SCHEMA_VERSION:
        migrator = _MIGRATIONS.get(version)
        if migrator is None:
            raise DocumentVersionError(
                f"no migration path from schema_version {version}",
                details={"received": version, "supported": sorted(SUPPORTED_VERSIONS)},
            )
        current = migrator(current)
        version = int(current.get("schema_version", version + 1))
    return current


def document_to_dict(document: MusicDocument) -> Dict[str, Any]:
    """Deterministic dict form: same document -> same bytes."""
    return document.model_dump(mode="json")


def document_to_json(document: MusicDocument) -> str:
    return json.dumps(document_to_dict(document), ensure_ascii=False, separators=(",", ":"))


def document_from_dict(payload: Dict[str, Any]) -> MusicDocument:
    if not isinstance(payload, dict):
        raise ValidationAppError("document payload must be a JSON object")
    migrated = migrate(payload)
    try:
        return MusicDocument.model_validate(migrated)
    except ValidationError as exc:
        raise ValidationAppError(
            "MusicDocument validation failed",
            details={"errors": _format_validation_errors(exc)},
        ) from exc


def document_from_json(raw: str) -> MusicDocument:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationAppError(
            "document is not valid JSON", details={"position": exc.pos, "reason": exc.msg}
        ) from exc
    return document_from_dict(payload)


def _format_validation_errors(exc: ValidationError) -> list:
    formatted = []
    for error in exc.errors():
        formatted.append(
            {"loc": [str(p) for p in error.get("loc", ())], "msg": error.get("msg", ""), "type": error.get("type", "")}
        )
    return formatted


def safe_document_from_json(raw: str) -> MusicDocument:
    """Used when reading persisted rows: a corrupt row is a server error, not a 422."""
    try:
        return document_from_json(raw)
    except AppError as exc:
        logger.error("corrupt MusicDocument payload: %s", exc.message)
        raise AppError(
            "stored MusicDocument payload is corrupt",
            code="DOCUMENT_CORRUPT",
            status_code=500,
        ) from exc
