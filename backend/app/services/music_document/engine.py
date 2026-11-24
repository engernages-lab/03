"""MusicDocument editing primitives.

Owner: pocket-music-core skill.  Every mutation funnels through here so that
`measure` / `beat` / `mapped_key` / `duration` invariants are maintained in one
place.  Grid and jianpu notation only *read* documents.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from app.core.errors import NotFoundError, ValidationAppError
from app.schemas.music_document import (
    EPSILON,
    MAX_EVENTS,
    MusicDocument,
    MusicTrack,
    NoteEvent,
    TimeSignature,
    new_id,
)
from app.services.keyboard.mapping import KeyboardMappingEngine
from app.services.music_document.timing import beats_to_seconds, locate_beat

# ---------------------------------------------------------------------------
# invariants
# ---------------------------------------------------------------------------

def recompute_positions(document: MusicDocument) -> None:
    """Refresh derived fields: measure, beat, duration."""
    for event in document.events:
        measure, beat = locate_beat(event.start_time, document.time_signature)
        event.measure = measure
        event.beat = beat
    document.duration = round(beats_to_seconds(document.max_end_beat(), document.tempo), 4)


def detect_chords(document: MusicDocument) -> None:
    """Group simultaneous notes of the same track into chords."""
    buckets: Dict[tuple, List[NoteEvent]] = {}
    for event in document.events:
        if event.pitch is None:
            event.chord_id = None
            continue
        key = (event.track_id, round(event.start_time, 6))
        buckets.setdefault(key, []).append(event)

    for (_track_id, _start), events in buckets.items():
        if len(events) >= 2:
            chord_id = events[0].chord_id or new_id("ch_")
            for event in events:
                event.chord_id = chord_id
        else:
            events[0].chord_id = None


def reindex(document: MusicDocument) -> MusicDocument:
    """Full re-derivation of every computed field.

    Call this after any structural change.  It never changes user-authored
    values (pitch, start_time, duration, velocity).
    """
    detect_chords(document)
    recompute_positions(document)
    KeyboardMappingEngine(document.keyboard_layout).apply(document)
    sort_events(document)
    return document


def sort_events(document: MusicDocument) -> None:
    full_order = [t.track_id for t in sorted(document.tracks, key=lambda t: t.index)]
    rank = {track_id: i for i, track_id in enumerate(full_order)}
    document.events.sort(key=lambda e: (e.start_time, rank.get(e.track_id, 0), e.pitch or -1))


# ---------------------------------------------------------------------------
# lookups
# ---------------------------------------------------------------------------

def require_track(document: MusicDocument, track_id: str) -> MusicTrack:
    track = document.track_by_id(track_id)
    if track is None:
        raise NotFoundError(
            f"Track {track_id!r} does not exist in this document",
            code="DOCUMENT_TRACK_MISSING",
            details={"track_id": track_id},
        )
    return track


def require_event(document: MusicDocument, event_id: str) -> NoteEvent:
    event = document.event_by_id(event_id)
    if event is None:
        raise NotFoundError(
            f"Event {event_id!r} not found", code="EVENT_NOT_FOUND", details={"event_id": event_id}
        )
    return event


# ---------------------------------------------------------------------------
# mutations
# ---------------------------------------------------------------------------

def add_event(
    document: MusicDocument,
    *,
    pitch: Optional[int],
    start_time: float,
    duration: float,
    track_id: Optional[str] = None,
    velocity: int = 96,
    kind: str = "note",
    chord_id: Optional[str] = None,
    tie_group: Optional[str] = None,
) -> NoteEvent:
    if len(document.events) >= MAX_EVENTS:
        raise ValidationAppError(
            f"document already holds the maximum of {MAX_EVENTS} events",
            code="DOCUMENT_TOO_LARGE",
            status_code=413,
        )
    if start_time < 0:
        raise ValidationAppError("start_time must be >= 0", code="INVALID_EVENT_TIME")
    if duration <= 0:
        raise ValidationAppError("duration must be > 0", code="INVALID_EVENT_TIME")
    if kind == "note" and pitch is None:
        raise ValidationAppError("note events require a pitch", code="INVALID_PITCH")
    if kind == "rest" and pitch is not None:
        raise ValidationAppError("rest events must not carry a pitch", code="INVALID_PITCH")

    resolved_track = track_id or document.tracks[0].track_id
    require_track(document, resolved_track)

    event = NoteEvent(
        event_id=new_id(),
        pitch=pitch,
        start_time=float(start_time),
        duration=float(duration),
        velocity=max(1, min(127, int(velocity))),
        track_id=resolved_track,
        kind="rest" if kind == "rest" else "note",
        chord_id=chord_id,
        tie_group=tie_group,
    )
    document.events.append(event)
    reindex(document)
    return event


def update_event(document: MusicDocument, event_id: str, patch: Dict[str, object]) -> NoteEvent:
    event = require_event(document, event_id)
    allowed = {"pitch", "start_time", "duration", "velocity", "track_id", "kind", "chord_id", "tie_group"}
    unknown = set(patch) - allowed
    if unknown:
        raise ValidationAppError(
            f"unsupported event fields: {sorted(unknown)}", code="INVALID_EVENT_PATCH"
        )

    data = event.model_dump()
    data.update({k: v for k, v in patch.items() if v is not None or k in {"pitch", "chord_id", "tie_group"}})

    if data["start_time"] is not None and float(data["start_time"]) < 0:
        raise ValidationAppError("start_time must be >= 0", code="INVALID_EVENT_TIME")
    if data["duration"] is not None and float(data["duration"]) <= 0:
        raise ValidationAppError("duration must be > 0", code="INVALID_EVENT_TIME")
    if data.get("track_id"):
        require_track(document, str(data["track_id"]))

    candidate = NoteEvent(**data)
    for field_name in ("pitch", "start_time", "duration", "velocity", "track_id", "kind", "chord_id", "tie_group"):
        setattr(event, field_name, getattr(candidate, field_name))
    reindex(document)
    return event


def delete_event(document: MusicDocument, event_id: str) -> None:
    event = require_event(document, event_id)
    document.events = [e for e in document.events if e.event_id != event.event_id]
    reindex(document)


def move_event_to_key(document: MusicDocument, event_id: str, key_id: str) -> NoteEvent:
    """Re-pitch an event to the pitch of ``key_id`` (layout change is unaffected)."""
    event = require_event(document, event_id)
    pitch = KeyboardMappingEngine(document.keyboard_layout).pitch_for_key(key_id)
    if pitch is None:
        raise ValidationAppError(
            f"key {key_id!r} does not exist in the current layout",
            code="KEYBOARD_KEY_NOT_FOUND",
            details={"key_id": key_id},
        )
    event.pitch = pitch
    reindex(document)
    return event


def transpose(document: MusicDocument, semitones: int, track_id: Optional[str] = None) -> int:
    """Transpose in place, clamping to the MIDI range. Returns the number changed."""
    changed = 0
    for event in document.events:
        if event.pitch is None:
            continue
        if track_id and event.track_id != track_id:
            continue
        new_pitch = event.pitch + semitones
        if 0 <= new_pitch <= 127:
            event.pitch = new_pitch
            changed += 1
    reindex(document)
    return changed


def quantize_events(document: MusicDocument, divisions: int = 4, track_id: Optional[str] = None) -> int:
    from app.services.music_document.timing import quantize

    changed = 0
    for event in document.events:
        if track_id and event.track_id != track_id:
            continue
        new_start = quantize(event.start_time, divisions)
        new_duration = max(1.0 / divisions, quantize(event.duration, divisions))
        if abs(new_start - event.start_time) > EPSILON or abs(new_duration - event.duration) > EPSILON:
            event.start_time = new_start
            event.duration = new_duration
            changed += 1
    reindex(document)
    return changed


def set_tempo(document: MusicDocument, tempo: float) -> MusicDocument:
    if not 20.0 <= tempo <= 400.0:
        raise ValidationAppError("tempo must be within 20..400", code="INVALID_TEMPO")
    document.tempo = float(tempo)
    d = document
    recompute_positions(d)
    return d


def set_time_signature(document: MusicDocument, numerator: int, denominator: int) -> MusicDocument:
    document.time_signature = TimeSignature(numerator=numerator, denominator=denominator)
    recompute_positions(document)
    return document


def add_track(document: MusicDocument, name: str, instrument: str = "piano") -> MusicTrack:
    if len(document.tracks) >= 64:
        raise ValidationAppError("too many tracks", code="TOO_MANY_TRACKS")
    track = MusicTrack(
        track_id=new_id("t"),
        name=name,
        instrument=instrument,
        index=len(document.tracks),
        color=document.tracks[0].color if document.tracks else "#3ddc97",
    )
    document.tracks.append(track)
    return track


def delete_track(document: MusicDocument, track_id: str) -> None:
    if len(document.tracks) <= 1:
        raise ValidationAppError(
            "a document must keep at least one track", code="LAST_TRACK"
        )
    require_track(document, track_id)
    document.tracks = [t for t in document.tracks if t.track_id != track_id]
    document.events = [e for e in document.events if e.track_id != track_id]
    reindex(document)


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------

def find_overlaps(document: MusicDocument) -> List[dict]:
    """Same-pitch, same-track, time-overlapping events (legato/voice conflicts)."""
    overlaps: List[dict] = []
    by_key: Dict[tuple, List[NoteEvent]] = {}
    for event in document.events:
        if event.pitch is None:
            continue
        by_key.setdefault((event.track_id, event.pitch), []).append(event)
    for (track_id, pitch), events in by_key.items():
        ordered = sorted(events, key=lambda e: e.start_time)
        for previous, current in zip(ordered, ordered[1:]):
            if current.start_time < previous.end_time - EPSILON:
                overlaps.append(
                    {
                        "track_id": track_id,
                        "pitch": pitch,
                        "first": previous.event_id,
                        "second": current.event_id,
                        "overlap_beats": round(previous.end_time - current.start_time, 6),
                    }
                )
    return overlaps


def validate_document(document: MusicDocument) -> List[dict]:
    """Collect non-fatal findings; fatal problems raise during model validation."""
    findings: List[dict] = []
    for overlap in find_overlaps(document):
        findings.append({"level": "warning", "code": "EVENT_OVERLAP", **overlap})

    engine = KeyboardMappingEngine(document.keyboard_layout)
    unmapped = engine.unmapped([e.pitch for e in document.events if e.pitch is not None])
    if unmapped:
        findings.append(
            {
                "level": "info",
                "code": "UNMAPPED_PITCHES",
                "pitches": unmapped,
                "message": "these pitches are outside the current keyboard layout",
            }
        )
    if not document.events:
        findings.append({"level": "info", "code": "EMPTY_DOCUMENT", "message": "document has no events"})
    return findings


def track_summary(document: MusicDocument) -> Iterable[dict]:
    for track in document.tracks:
        events = [e for e in document.events if e.track_id == track.track_id]
        yield {
            "track_id": track.track_id,
            "name": track.name,
            "events": len(events),
            "notes": sum(1 for e in events if e.kind == "note"),
            "rests": sum(1 for e in events if e.kind == "rest"),
        }
