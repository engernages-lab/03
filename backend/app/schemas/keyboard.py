"""Keyboard layout contract (owner: pocket-keyboard-mapping skill).

`KeyboardLayout` is embedded inside a `MusicDocument` so a document is
self-contained: exporting the JSON keeps the exact键位 the score was made with.
"""

from __future__ import annotations

import re
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")

KEY_COLORS = [
    "#3ddc97", "#22d3ee", "#8b5cf6", "#f5a524", "#fb7185",
    "#38bdf8", "#a3e635", "#f472b6", "#facc15", "#2dd4bf",
    "#c084fc", "#fda4af",
]


class KeyDefinition(BaseModel):
    """A single physical key of the pocket keyboard."""

    model_config = ConfigDict(extra="forbid")

    key_id: str = Field(min_length=1, max_length=48)
    label: str = Field(min_length=1, max_length=24)
    index: int = Field(ge=0, le=255)
    row: int = Field(default=0, ge=0, le=32)
    col: int = Field(default=0, ge=0, le=32)
    midi_pitch: Optional[int] = Field(default=None, ge=0, le=127)
    semitone_offset: Optional[int] = Field(default=None, ge=-96, le=96)
    color: str = "#3ddc97"
    octave: Optional[int] = Field(default=None, ge=-2, le=8)

    @field_validator("color")
    @classmethod
    def _validate_color(cls, value: str) -> str:
        if not HEX_COLOR.match(value):
            raise ValueError("color must be a #RRGGBB hex string")
        return value.lower()

    @model_validator(mode="after")
    def _needs_pitch_source(self) -> "KeyDefinition":
        if self.midi_pitch is None and self.semitone_offset is None:
            raise ValueError(
                f"key {self.key_id!r} must define either midi_pitch or semitone_offset"
            )
        return self


class KeyboardLayout(BaseModel):
    """A reusable pocket keyboard layout."""

    model_config = ConfigDict(extra="forbid")

    layout_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=40)
    description: str = Field(default="", max_length=280)
    root_note: int = Field(default=60, ge=0, le=127)
    key_count: int = Field(ge=1, le=36)
    octave_span: int = Field(default=1, ge=1, le=4)
    keys: List[KeyDefinition] = Field(min_length=1, max_length=36)
    is_builtin: bool = False

    @model_validator(mode="after")
    def _validate_layout(self) -> "KeyboardLayout":
        if self.key_count != len(self.keys):
            raise ValueError(
                f"key_count ({self.key_count}) must equal number of keys ({len(self.keys)})"
            )
        key_ids = [k.key_id for k in self.keys]
        if len(set(key_ids)) != len(key_ids):
            raise ValueError("duplicate key_id in layout")
        indexes = [k.index for k in self.keys]
        if len(set(indexes)) != len(indexes):
            raise ValueError("duplicate key index in layout")
        if sorted(indexes) != list(range(len(indexes))):
            raise ValueError("key index values must be contiguous starting at 0")
        absolute = [k.midi_pitch for k in self.keys if k.midi_pitch is not None]
        if len(set(absolute)) != len(absolute):
            raise ValueError("duplicate absolute midi_pitch in layout")
        return self

    def sorted_keys(self) -> List[KeyDefinition]:
        return sorted(self.keys, key=lambda k: k.index)


def default_layout(layout_id: str = "builtin:7-key-c-major") -> KeyboardLayout:
    """A 7-key diatonic pocket keyboard rooted at C4 (the V1.0-A default)."""
    scale = [(0, "1", "C"), (2, "2", "D"), (4, "3", "E"), (5, "4", "F"),
             (7, "5", "G"), (9, "6", "A"), (11, "7", "B")]
    keys = [
        KeyDefinition(
            key_id=f"k{index}",
            label=f"{name}4",
            index=index,
            row=0,
            col=index,
            midi_pitch=60 + offset,
            semitone_offset=offset,
            color=KEY_COLORS[index % len(KEY_COLORS)],
            octave=4,
        )
        for index, (offset, _degree, name) in enumerate(scale)
    ]
    return KeyboardLayout(
        layout_id=layout_id,
        name="默认七键 · C 大调",
        description="C4–B4 自然音阶，适合入门与简谱对照。",
        root_note=60,
        key_count=len(keys),
        octave_span=1,
        keys=keys,
        is_builtin=True,
    )


def chroma_layout(layout_id: str = "builtin:12-key-chromatic") -> KeyboardLayout:
    """A 12-key chromatic layout (one octave, C4–B4)."""
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    keys = [
        KeyDefinition(
            key_id=f"k{index}",
            label=f"{name}4",
            index=index,
            row=0,
            col=index,
            midi_pitch=60 + index,
            semitone_offset=index,
            color=KEY_COLORS[index % len(KEY_COLORS)],
            octave=4,
        )
        for index, name in enumerate(names)
    ]
    return KeyboardLayout(
        layout_id=layout_id,
        name="十二键 · 半音阶",
        description="C4–B4 半音阶，覆盖全部十二个音级。",
        root_note=60,
        key_count=len(keys),
        octave_span=1,
        keys=keys,
        is_builtin=True,
    )


def folded_layout(layout_id: str = "builtin:10-key-folded") -> KeyboardLayout:
    """A 10-key layout that folds two octaves onto the same keys."""
    degrees = [(0, "do"), (2, "re"), (4, "mi"), (5, "fa"), (7, "sol"),
               (9, "la"), (11, "si"), (12, "do'"), (14, "re'"), (16, "mi'")]
    keys = [
        KeyDefinition(
            key_id=f"k{index}",
            label=label,
            index=index,
            row=0 if index < 5 else 1,
            col=index % 5,
            semitone_offset=offset,
            color=KEY_COLORS[index % len(KEY_COLORS)],
        )
        for index, (offset, label) in enumerate(degrees)
    ]
    return KeyboardLayout(
        layout_id=layout_id,
        name="十键折叠 · 双八度",
        description="do–mi' 十键，覆盖一个半八度，用于折叠式口袋键盘。",
        root_note=60,
        key_count=len(keys),
        octave_span=2,
        keys=keys,
        is_builtin=True,
    )


BUILTIN_LAYOUTS = [default_layout(), chroma_layout(), folded_layout()]


def builtin_layout(layout_id: str) -> Optional[KeyboardLayout]:
    for layout in BUILTIN_LAYOUTS:
        if layout.layout_id == layout_id:
            return layout.model_copy(deep=True)
    return None


DEFAULT_LAYOUT_ID = "builtin:7-key-c-major"
