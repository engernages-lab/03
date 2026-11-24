"""Keyboard layout storage, validation and pitch <-> key mapping.

Owner: pocket-keyboard-mapping skill.  This module is the **only** place that
decides which key plays a given MIDI pitch.  Changing a layout recomputes
``mapped_key`` for every event and never touches ``pitch``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.schemas.keyboard import (
    BUILTIN_LAYOUTS,
    DEFAULT_LAYOUT_ID,
    KeyboardLayout,
    KeyDefinition,
    builtin_layout,
    default_layout,
)
from app.schemas.music_document import MusicDocument


@dataclass
class MappingResult:
    pitch: int
    key: Optional[KeyDefinition]
    fallback: bool = False

    @property
    def key_id(self) -> Optional[str]:
        return self.key.key_id if self.key else None


class KeyboardMappingEngine:
    """Deterministic pitch -> key resolution for one layout."""

    def __init__(self, layout: KeyboardLayout) -> None:
        self.layout = layout
        self._direct: Dict[int, KeyDefinition] = {}
        for key in layout.sorted_keys():
            pitch = self.absolute_pitch(key)
            if pitch is not None:
                self._direct.setdefault(pitch, key)
        self._by_id: Dict[str, KeyDefinition] = {k.key_id: k for k in layout.keys}

    # -- helpers -----------------------------------------------------------
    def absolute_pitch(self, key: KeyDefinition) -> Optional[int]:
        if key.midi_pitch is not None:
            return key.midi_pitch
        if key.semitone_offset is None:
            return None
        pitch = self.layout.root_note + key.semitone_offset
        return pitch if 0 <= pitch <= 127 else None

    def key(self, key_id: str) -> Optional[KeyDefinition]:
        return self._by_id.get(key_id)

    # -- mapping -----------------------------------------------------------
    def resolve(self, pitch: int) -> MappingResult:
        key = self._direct.get(pitch)
        if key is not None:
            return MappingResult(pitch=pitch, key=key, fallback=False)
        if self.layout.octave_span > 1:
            folded = self._resolve_folded(pitch)
            if folded is not None:
                return MappingResult(pitch=pitch, key=folded, fallback=True)
        return MappingResult(pitch=pitch, key=None, fallback=False)

    def _resolve_folded(self, pitch: int) -> Optional[KeyDefinition]:
        """Fold extra octaves onto the same physical keys (pocket keyboard)."""
        best: Optional[KeyDefinition] = None
        best_distance: Optional[int] = None
        for key in self.layout.sorted_keys():
            absolute = self.absolute_pitch(key)
            if absolute is None:
                continue
            if (absolute - pitch) % 12 != 0:
                continue
            distance = abs(absolute - pitch) // 12
            if distance == 0:
                continue
            if distance > self.layout.octave_span - 1:
                continue
            if best_distance is None or distance < best_distance:
                best, best_distance = key, distance
        return best

    def key_for_pitch(self, pitch: int) -> Optional[KeyDefinition]:
        return self.resolve(pitch).key

    def pitch_for_key(self, key_id: str) -> Optional[int]:
        key = self._by_id.get(key_id)
        if key is None:
            return None
        return self.absolute_pitch(key)

    def pitch_to_key_id(self) -> Dict[int, str]:
        mapping: Dict[int, str] = {}
        for pitch, key in sorted(self._direct.items()):
            mapping[pitch] = key.key_id
        if self.layout.octave_span > 1:
            for pitch in range(128):
                if pitch in mapping:
                    continue
                folded = self._resolve_folded(pitch)
                if folded is not None:
                    mapping[pitch] = folded.key_id
        return mapping

    def unmapped(self, pitches: List[int]) -> List[int]:
        return sorted({p for p in pitches if self.resolve(p).key is None})

    # -- document integration ---------------------------------------------
    def apply(self, document: MusicDocument) -> MusicDocument:
        """Recompute ``mapped_key`` for every sounding event."""
        for event in document.events:
            if event.pitch is None:
                event.mapped_key = None
                continue
            event.mapped_key = self.resolve(event.pitch).key_id
        return document


def apply_layout(document: MusicDocument, layout: Optional[KeyboardLayout] = None) -> MusicDocument:
    """Embed ``layout`` into the document and refresh every ``mapped_key``."""
    if layout is not None:
        document.keyboard_layout = layout
    KeyboardMappingEngine(document.keyboard_layout).apply(document)
    return document


def preview_layout(layout: KeyboardLayout, octaves: int = 2) -> List[dict]:
    """Expand a layout into key/preview rows for the visual editor."""
    engine = KeyboardMappingEngine(layout)
    rows: List[dict] = []
    for key in layout.sorted_keys():
        pitch = engine.absolute_pitch(key)
        rows.append(
            {
                "key_id": key.key_id,
                "label": key.label,
                "index": key.index,
                "row": key.row,
                "col": key.col,
                "color": key.color,
                "pitch": pitch,
                "pitch_name": pitch_name(pitch) if pitch is not None else None,
                "octave": key.octave,
            }
        )
    return rows


_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def pitch_name(pitch: int) -> str:
    if not 0 <= pitch <= 127:
        raise ValueError("pitch must be within 0..127")
    return f"{_NOTE_NAMES[pitch % 12]}{pitch // 12 - 1}"


# ---------------------------------------------------------------------------
# Registry helpers shared by the API and the document engine
# ---------------------------------------------------------------------------

def resolve_layout(
    layout_id: Optional[str],
    custom_layouts: Optional[Dict[str, KeyboardLayout]] = None,
) -> KeyboardLayout:
    """Resolve a layout id to a layout, falling back to the builtin default."""
    if not layout_id:
        return default_layout(DEFAULT_LAYOUT_ID)
    builtin = builtin_layout(layout_id)
    if builtin is not None:
        return builtin
    if custom_layouts and layout_id in custom_layouts:
        return custom_layouts[layout_id].model_copy(deep=True)
    raise NotFoundError(
        f"Keyboard layout {layout_id!r} not found", code="KEYBOARD_LAYOUT_NOT_FOUND"
    )


def validate_layout(layout: KeyboardLayout, existing_ids: List[str]) -> None:
    if layout.layout_id in existing_ids:
        raise ConflictError(
            f"Keyboard layout id {layout.layout_id!r} already exists",
            code="LAYOUT_DUPLICATE_ID",
        )
    if layout.key_count != len(layout.keys):
        raise ValidationAppError(
            "key_count does not match the number of keys", code="LAYOUT_KEY_COUNT_MISMATCH"
        )


def ensure_not_builtin(layout_id: str) -> None:
    if any(b.layout_id == layout_id for b in BUILTIN_LAYOUTS):
        raise ValidationAppError(
            "builtin layouts are read-only", code="LAYOUT_READONLY", status_code=403
        )
