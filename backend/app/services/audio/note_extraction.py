"""Audio -> note events using the Basic Pitch (ICASSP 2022) model.

Basic Pitch is a polyphonic transcription model released by Spotify's Audio
Intelligence Lab under Apache-2.0. On Windows with CPython < 3.11 the package
ships an ONNX graph (``nmp.onnx``) and runs on ``onnxruntime`` - no TensorFlow
install is required.

This module is the *only* place that turns audio into notes. It never invents
events: when the model is unavailable the caller must surface ``REQUIRES_MODEL``
instead of falling back to random or template data.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.core.logging import get_logger
from app.schemas.music_document import (
    MusicDocument,
    MusicTrack,
    NoteEvent,
    SourceMetadata,
    TimeSignature,
    empty_document,
    new_id,
)
from app.services.music_document.engine import reindex
from app.services.music_document.timing import (
    beats_per_measure,
    locate_beat,
    seconds_to_beats,
)

logger = get_logger(__name__)

MODEL_ID = "basic_pitch"
MODEL_NAME = "Basic Pitch"
MODEL_VERSION = "0.4.0"
MODEL_LICENSE = "Apache-2.0"
MODEL_SOURCE = "https://github.com/spotify/basic-pitch"

# Basic Pitch works at ~11 kHz internally and is trained on 22050 Hz audio.
EXPECTED_SAMPLE_RATE = 22_050

# Notation quantisation: one grid slot is a 16th note (4 divisions per beat).
QUANTISE_BEATS = 0.25


@dataclass(frozen=True)
class DetectedNote:
    """One note produced by the model, in seconds."""

    pitch: int
    start: float
    end: float
    amplitude: float

    @property
    def duration(self) -> float:
        return max(self.end - self.start, 1e-3)


def _load_module():
    """Import ``basic_pitch`` lazily so the API boots without the model."""
    try:
        return importlib.import_module("basic_pitch.inference")
    except Exception as exc:  # pragma: no cover - depends on optional install
        logger.warning("basic_pitch is not importable: %s", exc)
        return None


def _runtime_version() -> Optional[str]:
    try:
        ort = importlib.import_module("onnxruntime")
        return getattr(ort, "__version__", None)
    except Exception:  # pragma: no cover - optional
        return None


def model_status() -> Dict[str, Any]:
    """Capability descriptor used by /transcription/models and /capabilities."""
    inference = _load_module()
    available = inference is not None
    reason = None
    if not available:
        reason = (
            "basic-pitch 未安装或无法加载；安装命令："
            "pip install basic-pitch（Windows + Python<3.11 会自动使用 onnxruntime）"
        )
    return {
        "available": available,
        "model_id": MODEL_ID,
        "name": MODEL_NAME,
        "version": MODEL_VERSION,
        "license": MODEL_LICENSE,
        "source": MODEL_SOURCE,
        "runtime": f"onnxruntime {_runtime_version()}" if available else None,
        "polyphonic": True,
        "instrument_scope": ["piano", "keyboard", "melodic instruments", "voice"],
        "outputs": ["pitch", "onset", "offset", "velocity", "note confidence"],
        "capabilities": {
            "monophonic_melody": True,
            "polyphonic": True,
            "piano": True,
            "multi_instrument": False,
            "velocity": True,
            "confidence": True,
        },
        "reason": reason,
    }


def _merge_adjacent(notes: List[DetectedNote], *, gap: float = 0.06) -> List[DetectedNote]:
    """Join same-pitch segments the model split at an amplitude dip.

    Basic Pitch often re-articulates a sustained note when its envelope decays,
    producing two abutting events for one played note. Merging them keeps the
    notation readable and is standard post-processing, not data invention.
    """
    merged: List[DetectedNote] = []
    for note in sorted(notes, key=lambda item: (item.start, item.pitch)):
        previous = merged[-1] if merged else None
        if (
            previous is not None
            and previous.pitch == note.pitch
            and note.start - previous.end <= gap
        ):
            merged[-1] = DetectedNote(
                pitch=previous.pitch,
                start=previous.start,
                end=max(previous.end, note.end),
                amplitude=max(previous.amplitude, note.amplitude),
            )
        else:
            merged.append(note)
    return merged


def transcribe_file(
    path: Path,
    *,
    onset_threshold: float = 0.5,
    frame_threshold: float = 0.3,
    minimum_note_length_ms: float = 58.0,
    minimum_frequency: Optional[float] = None,
    maximum_frequency: Optional[float] = None,
    max_notes: int = 5_000,
) -> List[DetectedNote]:
    """Run the model and return real note events (seconds, MIDI pitch).

    Raises ``RuntimeError`` when the model is unavailable so callers can map it
    to ``REQUIRES_MODEL`` instead of silently producing an empty result.
    """
    inference = _load_module()
    if inference is None:
        raise RuntimeError("basic_pitch_unavailable")

    from basic_pitch import ICASSP_2022_MODEL_PATH

    logger.info("running %s on %s", MODEL_ID, path.name)
    _model_output, _midi_data, note_events = inference.predict(
        str(path),
        ICASSP_2022_MODEL_PATH,
        onset_threshold=onset_threshold,
        frame_threshold=frame_threshold,
        minimum_note_length=minimum_note_length_ms,
        minimum_frequency=minimum_frequency,
        maximum_frequency=maximum_frequency,
        melodia_trick=True,
    )

    notes: List[DetectedNote] = []
    for event in note_events:
        start, end, pitch, amplitude = float(event[0]), float(event[1]), int(event[2]), float(event[3])
        if end <= start:
            continue
        notes.append(
            DetectedNote(
                pitch=max(0, min(127, pitch)),
                start=max(0.0, start),
                end=max(0.0, end),
                amplitude=max(0.0, min(1.0, amplitude)),
            )
        )
    notes.sort(key=lambda note: (note.start, note.pitch))
    notes = _merge_adjacent(notes)
    if len(notes) > max_notes:
        logger.warning("model produced %s notes, truncating to %s", len(notes), max_notes)
        notes = notes[:max_notes]
    return notes


def _quantise(value: float) -> float:
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
    """Convert model output into the shared MusicDocument contract."""
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
        start_beats = _quantise(seconds_to_beats(note.start, document.tempo))
        duration_beats = max(QUANTISE_BEATS, _quantise(seconds_to_beats(note.duration, document.tempo)))
        # keep the note inside the measure it starts in (notation cannot render
        # a single event across a bar line without ties)
        measure, beat = locate_beat(start_beats, signature)
        room = beats_per_measure(signature) - (beat - 1.0)
        duration_beats = min(duration_beats, max(QUANTISE_BEATS, room))

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
                confidence=round(note.amplitude, 4),
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
