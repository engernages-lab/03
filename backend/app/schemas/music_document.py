"""Core music data contract (owner: pocket-music-core skill).

`MusicDocument` is the single source of truth for every score in PocketScore AI.
Grid notation and jianpu notation are both compiled from it - they never store
their own note data.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.keyboard import DEFAULT_LAYOUT_ID, KeyboardLayout, default_layout

CURRENT_SCHEMA_VERSION = 1
MAX_EVENTS = 50_000
EPSILON = 1e-6

VALID_KEY_SIGNATURES = {
    "C", "G", "D", "A", "E", "B", "F#", "C#", "F", "Bb", "Eb", "Ab", "Db", "Gb",
    "Am", "Em", "Bm", "F#m", "C#m", "G#m", "D#m", "A#m", "Dm", "Gm", "Cm", "Fm", "Bbm", "Ebm",
}

EventKind = Literal["note", "rest"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str = "") -> str:
    raw = uuid.uuid4().hex[:12]
    return f"{prefix}{raw}" if prefix else raw


class TimeSignature(BaseModel):
    model_config = ConfigDict(extra="forbid")

    numerator: int = Field(default=4, ge=1, le=32)
    denominator: int = Field(default=4)

    @field_validator("denominator")
    @classmethod
    def _power_of_two(cls, value: int) -> int:
        if value not in (1, 2, 4, 8, 16):
            raise ValueError("denominator must be one of 1, 2, 4, 8, 16")
        return value

    @property
    def beats_per_measure(self) -> float:
        """Length of a measure expressed in quarter-note beats."""
        return self.numerator * 4.0 / self.denominator

    def as_label(self) -> str:
        return f"{self.numerator}/{self.denominator}"


class MusicTrack(BaseModel):
    model_config = ConfigDict(extra="forbid")

    track_id: str = Field(min_length=1, max_length=48)
    name: str = Field(default="Track 1", min_length=1, max_length=80)
    instrument: str = Field(default="piano", max_length=64)
    channel: Optional[int] = Field(default=None, ge=0, le=15)
    index: int = Field(default=0, ge=0, le=63)
    color: str = "#3ddc97"
    muted: bool = False


class NoteEvent(BaseModel):
    """A note or an explicit rest on the beat-based timeline."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1, max_length=48)
    pitch: Optional[int] = Field(default=None, ge=0, le=127)
    start_time: float = Field(ge=0.0)
    duration: float = Field(gt=0.0)
    velocity: int = Field(default=96, ge=1, le=127)
    track_id: str = Field(min_length=1, max_length=48)
    measure: int = Field(default=1, ge=1)
    beat: float = Field(default=1.0, ge=0.0)
    mapped_key: Optional[str] = Field(default=None, max_length=48)
    kind: EventKind = "note"
    chord_id: Optional[str] = Field(default=None, max_length=48)
    tie_group: Optional[str] = Field(default=None, max_length=48)

    @model_validator(mode="after")
    def _kind_matches_pitch(self) -> "NoteEvent":
        if self.kind == "note" and self.pitch is None:
            raise ValueError("note events require a pitch")
        if self.kind == "rest" and self.pitch is not None:
            raise ValueError("rest events must not carry a pitch")
        return self

    @property
    def end_time(self) -> float:
        return self.start_time + self.duration


class GridSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    divisions: int = Field(default=4, ge=1, le=16)
    show_key_names: bool = True
    show_velocity: bool = False
    color_mode: Literal["key", "pitch", "velocity"] = "key"


class JianpuSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    show_key_labels: bool = True
    octave_style: Literal["dots", "primes"] = "dots"
    max_notes_per_line: int = Field(default=16, ge=4, le=64)
    # Chromatic notes are a semitone away from two degrees; this picks the
    # spelling (e.g. C#4 -> "#1" vs "b2").
    accidental_style: Literal["sharp", "flat"] = "sharp"


class NotationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grid: GridSettings = Field(default_factory=GridSettings)
    jianpu: JianpuSettings = Field(default_factory=JianpuSettings)


class SourceMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal[
        "manual", "midi", "local_file", "subsonic", "apple_music", "spotify",
        "netease", "qqmusic", "transcription",
    ] = "manual"
    filename: Optional[str] = Field(default=None, max_length=255)
    provider: Optional[str] = Field(default=None, max_length=64)
    provider_track_id: Optional[str] = Field(default=None, max_length=128)
    imported_at: Optional[datetime] = None
    notes: Optional[str] = Field(default=None, max_length=2000)


class MusicDocument(BaseModel):
    """The unified score document."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = CURRENT_SCHEMA_VERSION
    document_id: str = Field(default_factory=lambda: new_id())
    title: str = Field(default="未命名谱面", min_length=1, max_length=200)
    artist: str = Field(default="未知艺人", max_length=200)
    tempo: float = Field(default=120.0, ge=20.0, le=400.0)
    time_signature: TimeSignature = Field(default_factory=TimeSignature)
    key_signature: str = "C"
    duration: float = Field(default=0.0, ge=0.0)
    tracks: List[MusicTrack] = Field(default_factory=list)
    events: List[NoteEvent] = Field(default_factory=list)
    keyboard_layout: KeyboardLayout = Field(default_factory=lambda: default_layout(DEFAULT_LAYOUT_ID))
    notation_settings: NotationSettings = Field(default_factory=NotationSettings)
    source_metadata: SourceMetadata = Field(default_factory=SourceMetadata)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    # -- validators --------------------------------------------------------
    @field_validator("key_signature")
    @classmethod
    def _validate_key(cls, value: str) -> str:
        cleaned = value.strip()
        if cleaned not in VALID_KEY_SIGNATURES:
            raise ValueError(
                f"unsupported key_signature {value!r}; expected one of "
                f"{sorted(VALID_KEY_SIGNATURES)}"
            )
        return cleaned

    @model_validator(mode="after")
    def _validate_references(self) -> "MusicDocument":
        if not self.tracks:
            raise ValueError("a document must contain at least one track")
        track_ids = {t.track_id for t in self.tracks}
        if len(track_ids) != len(self.tracks):
            raise ValueError("duplicate track_id")
        seen = set()
        for event in self.events:
            if event.track_id not in track_ids:
                raise ValueError(f"event {event.event_id} references unknown track {event.track_id}")
            if event.event_id in seen:
                raise ValueError(f"duplicate event_id {event.event_id}")
            seen.add(event.event_id)
        if len(self.events) > MAX_EVENTS:
            raise ValueError(f"document exceeds the {MAX_EVENTS} event limit")
        return self

    # -- convenience -------------------------------------------------------
    @property
    def beats_per_measure(self) -> float:
        return self.time_signature.beats_per_measure

    def track_by_id(self, track_id: str) -> Optional[MusicTrack]:
        return next((t for t in self.tracks if t.track_id == track_id), None)

    def event_by_id(self, event_id: str) -> Optional[NoteEvent]:
        return next((e for e in self.events if e.event_id == event_id), None)

    def max_end_beat(self) -> float:
        if not self.events:
            return 0.0
        return max(e.end_time for e in self.events)

    def total_measures(self) -> int:
        bpm = self.beats_per_measure
        if bpm <= 0:
            return 1
        end = self.max_end_beat()
        return max(1, int((end - EPSILON) // bpm) + 1)

    def beat_to_seconds(self, beats: float) -> float:
        return beats * 60.0 / self.tempo

    def seconds_to_beat(self, seconds: float) -> float:
        return seconds * self.tempo / 60.0


def empty_document(
    title: str = "未命名谱面",
    artist: str = "未知艺人",
    tempo: float = 120.0,
    time_signature: Optional[TimeSignature] = None,
    key_signature: str = "C",
    keyboard_layout: Optional[KeyboardLayout] = None,
    source: Optional[SourceMetadata] = None,
) -> MusicDocument:
    """Build a valid one-track document ready for editing."""
    from app.services.music_document.engine import reindex

    document = MusicDocument(
        title=title,
        artist=artist,
        tempo=tempo,
        time_signature=time_signature or TimeSignature(),
        key_signature=key_signature,
        tracks=[MusicTrack(track_id="t1", name="主旋律", instrument="piano", index=0)],
        keyboard_layout=keyboard_layout or default_layout(DEFAULT_LAYOUT_ID),
        source_metadata=source or SourceMetadata(),
    )
    return reindex(document)
