"""Persistence for custom keyboard layouts (builtins live in code)."""

from __future__ import annotations

import json
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.models.music import KeyboardLayoutRecord
from app.schemas.keyboard import (
    BUILTIN_LAYOUTS,
    DEFAULT_LAYOUT_ID,
    KeyboardLayout,
    KeyDefinition,
    builtin_layout,
    default_layout,
)
from app.services.keyboard.mapping import ensure_not_builtin, preview_layout


def _to_model(record: KeyboardLayoutRecord) -> KeyboardLayout:
    try:
        keys = [KeyDefinition.model_validate(raw) for raw in json.loads(record.keys_json)]
    except (json.JSONDecodeError, ValueError) as exc:  # pragma: no cover - defensive
        raise ValidationAppError(
            "stored keyboard layout is corrupt", code="LAYOUT_CORRUPT", status_code=500
        ) from exc
    return KeyboardLayout(
        layout_id=record.id,
        name=record.name,
        description=record.description,
        root_note=record.root_note,
        key_count=record.key_count,
        octave_span=record.octave_span,
        keys=keys,
        is_builtin=record.is_builtin,
    )


def list_layouts(session: Session, include_builtin: bool = True) -> List[KeyboardLayout]:
    layouts: List[KeyboardLayout] = []
    if include_builtin:
        layouts.extend(layout.model_copy(deep=True) for layout in BUILTIN_LAYOUTS)
    rows = session.execute(select(KeyboardLayoutRecord).order_by(KeyboardLayoutRecord.created_at)).scalars()
    layouts.extend(_to_model(row) for row in rows)
    return layouts


def get_layout(session: Session, layout_id: str) -> KeyboardLayout:
    builtin = builtin_layout(layout_id)
    if builtin is not None:
        return builtin
    record = session.get(KeyboardLayoutRecord, layout_id)
    if record is None:
        raise NotFoundError(
            f"Keyboard layout {layout_id!r} not found",
            code="KEYBOARD_LAYOUT_NOT_FOUND",
            details={"layout_id": layout_id},
        )
    return _to_model(record)


def create_layout(session: Session, layout: KeyboardLayout) -> KeyboardLayout:
    if builtin_layout(layout.layout_id) is not None:
        raise ConflictError(
            f"layout id {layout.layout_id!r} collides with a builtin layout",
            code="LAYOUT_DUPLICATE_ID",
        )
    if session.get(KeyboardLayoutRecord, layout.layout_id) is not None:
        raise ConflictError(
            f"layout id {layout.layout_id!r} already exists", code="LAYOUT_DUPLICATE_ID"
        )
    record = KeyboardLayoutRecord(
        id=layout.layout_id,
        name=layout.name,
        description=layout.description,
        root_note=layout.root_note,
        key_count=layout.key_count,
        octave_span=layout.octave_span,
        keys_json=json.dumps([k.model_dump(mode="json") for k in layout.keys], ensure_ascii=False),
        is_builtin=False,
    )
    session.add(record)
    session.commit()
    return _to_model(record)


def update_layout(session: Session, layout_id: str, layout: KeyboardLayout) -> KeyboardLayout:
    ensure_not_builtin(layout_id)
    record = session.get(KeyboardLayoutRecord, layout_id)
    if record is None:
        raise NotFoundError(
            f"Keyboard layout {layout_id!r} not found", code="KEYBOARD_LAYOUT_NOT_FOUND"
        )
    if layout.layout_id != layout_id:
        raise ValidationAppError(
            "layout_id in payload must match the path", code="LAYOUT_ID_MISMATCH"
        )
    record.name = layout.name
    record.description = layout.description
    record.root_note = layout.root_note
    record.key_count = layout.key_count
    record.octave_span = layout.octave_span
    record.keys_json = json.dumps([k.model_dump(mode="json") for k in layout.keys], ensure_ascii=False)
    session.commit()
    return _to_model(record)


def delete_layout(session: Session, layout_id: str) -> None:
    ensure_not_builtin(layout_id)
    record = session.get(KeyboardLayoutRecord, layout_id)
    if record is None:
        raise NotFoundError(
            f"Keyboard layout {layout_id!r} not found", code="KEYBOARD_LAYOUT_NOT_FOUND"
        )
    session.delete(record)
    session.commit()


def duplicate_layout(session: Session, layout_id: str, name: Optional[str] = None) -> KeyboardLayout:
    source = get_layout(session, layout_id)
    clone = source.model_copy(deep=True)
    from app.schemas.music_document import new_id

    clone.layout_id = new_id("layout_")
    clone.name = name or f"{source.name} 副本"
    clone.is_builtin = False
    return create_layout(session, clone)


def export_layout(session: Session, layout_id: str) -> Dict:
    layout = get_layout(session, layout_id)
    return {"pocketscore_layout": True, "version": 1, "layout": layout.model_dump(mode="json")}


def import_layout(session: Session, payload: Dict) -> KeyboardLayout:
    if not isinstance(payload, dict):
        raise ValidationAppError("layout payload must be an object", code="LAYOUT_IMPORT_INVALID")
    raw = payload.get("layout", payload)
    try:
        layout = KeyboardLayout.model_validate(raw)
    except ValueError as exc:
        raise ValidationAppError(
            "imported file is not a valid keyboard layout",
            code="LAYOUT_IMPORT_INVALID",
            details={"reason": str(exc)},
        ) from exc
    layout.is_builtin = False
    if builtin_layout(layout.layout_id) is not None or session.get(
        KeyboardLayoutRecord, layout.layout_id
    ):
        from app.schemas.music_document import new_id

        layout.layout_id = new_id("layout_")
        layout.name = f"{layout.name} (导入)"
    return create_layout(session, layout)


def restore_default(session: Session) -> KeyboardLayout:
    """Return the builtin default layout; recreates it if a custom one shadowed it."""
    return default_layout(DEFAULT_LAYOUT_ID)


def layout_preview(session: Session, layout_id: str) -> Dict:
    layout = get_layout(session, layout_id)
    return {
        "layout": layout.model_dump(mode="json"),
        "keys": preview_layout(layout),
        "pitch_map": {str(pitch): key for pitch, key in layout_preview_map(layout).items()},
    }


def layout_preview_map(layout: KeyboardLayout) -> Dict[int, str]:
    from app.services.keyboard.mapping import KeyboardMappingEngine

    return KeyboardMappingEngine(layout).pitch_to_key_id()
