"""Edit operations and dual-notation synchronisation.

Owner: pocket-jianpu-notation skill (sync contract) + pocket-grid-notation
(edit instruction set).  Every edit - from either notation view - is expressed
as an operation list and applied to the single `MusicDocument`, which is then
re-compiled into both view models.  There is no per-view note storage, so the
two notations cannot drift apart.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.errors import ValidationAppError
from app.schemas.keyboard import KeyboardLayout
from app.schemas.music_document import MusicDocument
from app.services import music_document as core
from app.services.keyboard.mapping import apply_layout

EditOpName = Literal[
    "add_note",
    "add_rest",
    "update_note",
    "delete_note",
    "move_note",
    "transpose",
    "quantize",
    "set_tempo",
    "set_time_signature",
    "add_track",
    "delete_track",
    "set_layout",
]


class EditOperation(BaseModel):
    """One atomic change requested by either notation editor."""

    model_config = ConfigDict(extra="forbid")

    op: EditOpName
    event_id: Optional[str] = None
    pitch: Optional[int] = Field(default=None, ge=0, le=127)
    start_time: Optional[float] = Field(default=None, ge=0.0)
    duration: Optional[float] = Field(default=None, gt=0.0)
    velocity: Optional[int] = Field(default=None, ge=1, le=127)
    track_id: Optional[str] = None
    key_id: Optional[str] = None
    semitones: Optional[int] = Field(default=None, ge=-48, le=48)
    divisions: Optional[int] = Field(default=None, ge=1, le=16)
    numerator: Optional[int] = Field(default=None, ge=1, le=32)
    denominator: Optional[int] = None
    tempo: Optional[float] = Field(default=None, ge=20.0, le=400.0)
    track_name: Optional[str] = None
    patch: Optional[Dict[str, Any]] = None
    layout: Optional[KeyboardLayout] = None

    @model_validator(mode="after")
    def _required_fields(self) -> "EditOperation":
        needs_event = {
            "update_note": False,
            "delete_note": True,
            "move_note": True,
        }
        if self.op in needs_event and not self.event_id:
            raise ValueError(f"op {self.op} requires event_id")
        if self.op in ("move_note",) and not self.key_id:
            raise ValueError("op move_note requires key_id")
        if self.op == "add_note" and self.pitch is None:
            raise ValueError("op add_note requires pitch")
        if self.op in ("add_note", "add_rest") and (self.start_time is None or self.duration is None):
            raise ValueError(f"op {self.op} requires start_time and duration")
        if self.op == "set_time_signature" and (self.numerator is None or self.denominator is None):
            raise ValueError("op set_time_signature requires numerator and denominator")
        if self.op == "set_tempo" and self.tempo is None:
            raise ValueError("op set_tempo requires tempo")
        if self.op == "set_layout" and self.layout is None:
            raise ValueError("op set_layout requires layout")
        if self.op == "update_note" and not self.patch:
            raise ValueError("op update_note requires a patch")
        return self


class EditResult(BaseModel):
    document: MusicDocument
    applied: int
    touched_event_ids: List[str] = Field(default_factory=list)


def apply_operations(document: MusicDocument, operations: List[EditOperation]) -> EditResult:
    """Apply a batch atomically on a copy; the caller persists on success."""
    working = document.model_copy(deep=True)
    touched: List[str] = []

    for operation in operations:
        op = operation.op
        if op == "add_note":
            event = core.add_event(
                working,
                pitch=operation.pitch,
                start_time=float(operation.start_time or 0.0),
                duration=float(operation.duration or 0.0),
                track_id=operation.track_id,
                velocity=operation.velocity or 96,
                kind="note",
            )
            touched.append(event.event_id)
        elif op == "add_rest":
            event = core.add_event(
                working,
                pitch=None,
                start_time=float(operation.start_time or 0.0),
                duration=float(operation.duration or 0.0),
                track_id=operation.track_id,
                velocity=operation.velocity or 96,
                kind="rest",
            )
            touched.append(event.event_id)
        elif op == "update_note":
            patch = dict(operation.patch or {})
            patch = {k: v for k, v in patch.items() if v is not None}
            event = core.update_event(working, operation.event_id or "", patch)
            touched.append(event.event_id)
        elif op == "delete_note":
            event = core.require_event(working, operation.event_id or "")
            core.delete_event(working, event.event_id)
            touched.append(event.event_id)
        elif op == "move_note":
            event = core.move_event_to_key(working, operation.event_id or "", operation.key_id or "")
            touched.append(event.event_id)
        elif op == "transpose":
            core.transpose(working, int(operation.semitones or 0), operation.track_id)
        elif op == "quantize":
            core.quantize_events(working, int(operation.divisions or 4), operation.track_id)
        elif op == "set_tempo":
            core.set_tempo(working, float(operation.tempo or 120.0))
        elif op == "set_time_signature":
            core.set_time_signature(working, int(operation.numerator or 4), int(operation.denominator or 4))
        elif op == "add_track":
            track = core.add_track(working, operation.track_name or "新轨道")
            touched.append(track.track_id)
        elif op == "delete_track":
            core.delete_track(working, operation.track_id or "")
        elif op == "set_layout":
            apply_layout(working, operation.layout)
        else:  # pragma: no cover - guarded by the Literal type
            raise ValidationAppError(f"unsupported edit op {op!r}", code="UNKNOWN_EDIT_OP")

    core.reindex(working)
    return EditResult(document=working, applied=len(operations), touched_event_ids=touched)
