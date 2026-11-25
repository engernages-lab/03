"""Detected notes -> MusicDocument (single conversion site for audio input)."""

from __future__ import annotations

from typing import List, Optional, Tuple

from app.schemas.music_document import (
    MusicDocument,
    MusicTrack,
    NoteEvent,
    SourceMetadata,
    TimeSignature,
    empty_document,
    new_id,
)
from app.services.audio.transcription.config import DetectedNote
from app.services.audio.transcription.inference import MODEL_ID, MODEL_VERSION
from app.services.music_document.engine import reindex
from app.services.music_document.timing import (
    beats_per_measure,
    locate_beat,
    seconds_to_beats,
)

# Notation quantisation: one grid slot is a 16th note (4 divisions per beat).
QUANTISE_BEATS = 0.25


def quantise(value: float) -> float:
    return round(value / QUANTISE_BEATS) * QUANTISE_BEATS


def build_document(
    notes: List[DetectedNote],
    *,
    tempo: float,
    title: str,
    artist: str = "AI 扒谱",
    time_signature: Optional[TimeSignature] = None,
    source_audio_id: Optional[str] = None,
    filename: Optional[str] = None,
    extra_notes: Optional[str] = None,
) -> MusicDocument:
    """Convert detected notes into the shared MusicDocument contract."""
    signature = time_signature or TimeSignature()
    document = empty_document(
        title=title,
        artist=artist,
        tempo=max(20.0, min(300.0, tempo)),
        time_signature=signature,
        source=SourceMetadata(
            kind="transcription",
            filename=filename,
            provider=MODEL_ID,
            notes=extra_notes,
            recognition_model=MODEL_ID,
            recognition_version=MODEL_VERSION,
            source_audio_asset_id=source_audio_id,
        ),
    )
    track_id = document.tracks[0].track_id
    document.tracks = [
        MusicTrack(track_id=track_id, name="扒谱旋律", instrument="piano", index=0)
    ]

    events: List[NoteEvent] = []
    for note in notes:
        start_beats = quantise(seconds_to_beats(note.start, document.tempo))
        duration_beats = max(
            QUANTISE_BEATS, quantise(seconds_to_beats(note.duration, document.tempo))
        )
        measure, beat = locate_beat(start_beats, signature)
        room = beats_per_measure(signature) - (beat - 1.0)
        duration_beats = min(duration_beats, max(QUANTISE_BEATS, room))

        confidence = note.confidence
        if confidence is None:
            confidence = round(min(0.95, max(0.0, note.amplitude * 0.85)), 4)

        events.append(
            NoteEvent(
                event_id=new_id("ev"),
                pitch=note.pitch,
                start_time=start_beats,
                duration=duration_beats,
                velocity=max(1, min(127, int(round(note.amplitude * 127)))),
                track_id=track_id,
                measure=measure,
                beat=beat,
                confidence=confidence,
            )
        )

    document.events = events
    document = reindex(document)
    _assign_chords(document)
    return document


def _assign_chords(document: MusicDocument) -> None:
    """Group events that start together so both notations stack them."""
    tolerance = QUANTISE_BEATS / 2
    pending: List[Tuple[float, str]] = []
    for event in sorted(document.events, key=lambda item: (item.start_time, item.pitch or 0)):
        match = next(
            (chord for start, chord in pending if abs(start - event.start_time) <= tolerance),
            None,
        )
        if match is None:
            chord_id = new_id("ch")
            pending.append((event.start_time, chord_id))
            event.chord_id = chord_id
        else:
            event.chord_id = match
