"""Jianpu (numbered) notation engine.

Owner: pocket-jianpu-notation skill.  Pure function from MusicDocument to a
render-ready view model.  Pitch -> number conversion happens here and nowhere
else; the frontend only draws ``token`` / ``octave`` / ``duration_label``.
"""

from __future__ import annotations

from typing import Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field

from app.schemas.keyboard import KeyboardLayout
from app.schemas.music_document import EPSILON, MusicDocument
from app.services.keyboard.mapping import KeyboardMappingEngine
from app.services.notation.keys import (
    KeyContext,
    degree_for_pitch,
    degree_label,
    parse_key_signature,
)

# Base duration symbols, in quarter-note beats.
BASE_DURATIONS: List[Tuple[float, str]] = [
    (4.0, "—"),   # whole note
    (2.0, "-"),   # half note
    (1.0, ""),    # quarter note
    (0.5, "_"),   # eighth note
    (0.25, "="),  # sixteenth note
]

TieState = Literal["start", "continue", "stop"]


class JianpuNote(BaseModel):
    event_id: str
    pitch: Optional[int] = None
    token: str = "0"
    degree: Optional[int] = None
    accidental: Optional[str] = None
    octave: int = 0
    duration_label: str = ""
    dots: int = 0
    approximate: bool = False
    tie: Optional[TieState] = None
    is_rest: bool = False
    chord_id: Optional[str] = None
    chord_size: int = 1
    chord_index: int = 0
    is_chord_head: bool = True
    mapped_key: Optional[str] = None
    key_label: Optional[str] = None
    width: int = 1
    # V1.1-A: per-note model confidence (None for manual/MIDI events)
    confidence: Optional[float] = None
    start_time: float = 0.0
    duration: float = 0.0
    beat_in_measure: float = 1.0


class JianpuMeasure(BaseModel):
    measure: int
    start_beat: float
    beats: float
    system_index: int = 0
    notes: List[JianpuNote] = Field(default_factory=list)


class JianpuStats(BaseModel):
    notes: int = 0
    rests: int = 0
    chords: int = 0
    measures: int = 0
    accidentals: int = 0
    ties: int = 0
    unmapped: int = 0
    approximate_durations: int = 0


class JianpuViewModel(BaseModel):
    document_id: str
    title: str
    artist: str
    key_signature: str
    tonic: str
    mode: str
    tempo: float
    time_signature: str
    layout_id: str
    layout_name: str
    max_notes_per_line: int
    measures: List[JianpuMeasure] = Field(default_factory=list)
    key_labels: Dict[str, str] = Field(default_factory=dict)
    stats: JianpuStats = Field(default_factory=JianpuStats)


def duration_symbol(beats: float) -> Tuple[str, int, bool]:
    """Return ``(symbol, dots, approximate)`` for a duration in beats."""
    if beats <= 0:
        return "", 0, True
    for base, symbol in BASE_DURATIONS:
        if abs(beats - base) < EPSILON:
            return symbol, 0, False
        if abs(beats - base * 1.5) < EPSILON:
            return symbol, 1, False
        if abs(beats - base * 0.5) < EPSILON and base >= 1.0:
            # e.g. 0.5 already handled; keeps the table honest for odd inputs
            pass
    # Nearest base duration (log distance) - flagged as approximate.
    best_symbol, best_distance = "", float("inf")
    for base, symbol in BASE_DURATIONS:
        distance = abs((beats * 4.0) - (base * 4.0))
        if distance < best_distance:
            best_symbol, best_distance = symbol, distance
    return best_symbol, 0, True


def compile_jianpu(
    document: MusicDocument,
    layout: Optional[KeyboardLayout] = None,
    key_signature: Optional[str] = None,
) -> JianpuViewModel:
    layout = layout or document.keyboard_layout
    key = parse_key_signature(key_signature or document.key_signature)
    engine = KeyboardMappingEngine(layout)

    stats = JianpuStats()
    measures: List[JianpuMeasure] = []
    measures_count = max(1, document.total_measures())
    from app.services.music_document.timing import beats_per_measure, measure_start

    measure_beats = beats_per_measure(document.time_signature)
    for number in range(1, measures_count + 1):
        measures.append(
            JianpuMeasure(
                measure=number,
                start_beat=measure_start(number, document.time_signature),
                beats=measure_beats,
            )
        )

    # Ties: same pitch in the same track where the next event starts exactly when
    # the previous ends.
    tie_map: Dict[str, str] = {}
    by_pitch: Dict[Tuple[str, int], List] = {}
    for event in document.events:
        if event.kind == "note" and event.pitch is not None:
            by_pitch.setdefault((event.track_id, event.pitch), []).append(event)
    for events in by_pitch.values():
        ordered = sorted(events, key=lambda e: e.start_time)
        for previous, current in zip(ordered, ordered[1:]):
            if abs(current.start_time - (previous.start_time + previous.duration)) < EPSILON:
                tie_map[previous.event_id] = "start" if previous.event_id not in tie_map else "continue"
                tie_map[current.event_id] = "stop"

    # Group chord members so the frontend can stack them.
    chord_members: Dict[str, List] = {}
    for event in document.events:
        if event.chord_id:
            chord_members.setdefault(event.chord_id, []).append(event)
    for members in chord_members.values():
        members.sort(key=lambda e: e.pitch or 0)

    key_labels: Dict[str, str] = {}
    for event in document.events:
        if event.pitch is None:
            continue
        key_definition = engine.key_for_pitch(event.pitch)
        if key_definition is not None:
            key_labels[str(event.pitch)] = key_definition.label

    for event in document.events:
        note = _build_note(
            event,
            key,
            engine,
            tie_map,
            chord_members,
            key_labels,
            stats,
            prefer_flat=document.notation_settings.jianpu.accidental_style == "flat",
        )
        target = measures[min(max(note_measure(event), 1), len(measures)) - 1]
        target.notes.append(note)

    for measure in measures:
        measure.notes.sort(key=lambda n: (n.start_time, n.chord_index))
        if any(note.chord_id for note in measure.notes):
            _ensure_chord_consistency(measure)

    stats.measures = len(measures)
    stats.chords = len(chord_members)
    stats.ties = len(tie_map)

    # Lay measures out into systems respecting max_notes_per_line.
    line_budget = max(4, document.notation_settings.jianpu.max_notes_per_line)
    system_index = 0
    used = 0
    for measure in measures:
        size = max(1, len(measure.notes))
        if used and used + size > line_budget:
            system_index += 1
            used = 0
        measure.system_index = system_index
        used += size

    return JianpuViewModel(
        document_id=document.document_id,
        title=document.title,
        artist=document.artist,
        key_signature=key.label,
        tonic=_tonic_name(key),
        mode=key.mode,
        tempo=document.tempo,
        time_signature=document.time_signature.as_label(),
        layout_id=layout.layout_id,
        layout_name=layout.name,
        max_notes_per_line=line_budget,
        measures=measures,
        key_labels=key_labels,
        stats=stats,
    )


def note_measure(event) -> int:
    return max(1, event.measure)


def _tonic_name(key: KeyContext) -> str:
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    return names[key.tonic_pc]


def _build_note(
    event,
    key: KeyContext,
    engine: KeyboardMappingEngine,
    tie_map: Dict[str, str],
    chord_members: Dict[str, List],
    key_labels: Dict[str, str],
    stats: JianpuStats,
    prefer_flat: bool = False,
) -> JianpuNote:
    symbol, dots, approximate = duration_symbol(event.duration)
    width = max(1, int(round(event.duration * 4)))
    mapping = engine.resolve(event.pitch) if event.pitch is not None else None
    key_definition = mapping.key if mapping else None

    if event.kind == "rest" or event.pitch is None:
        stats.rests += 1
        if approximate:
            stats.approximate_durations += 1
        return JianpuNote(
            event_id=event.event_id,
            pitch=None,
            token="0",
            is_rest=True,
            duration_label=symbol,
            dots=dots,
            approximate=approximate,
            tie=tie_map.get(event.event_id),
            mapped_key=None,
            key_label=None,
            width=width,
            start_time=event.start_time,
            duration=event.duration,
            beat_in_measure=event.beat,
        )

    degree, accidental, octave = degree_for_pitch(event.pitch, key, prefer_flat=prefer_flat)
    if accidental:
        stats.accidentals += 1
    members = chord_members.get(event.chord_id or "", [])
    chord_index = 0
    if event.chord_id and members:
        chord_index = next(
            (index for index, member in enumerate(members) if member.event_id == event.event_id), 0
        )
    stats.notes += 1
    if approximate:
        stats.approximate_durations += 1
    if key_definition is None:
        stats.unmapped += 1

    return JianpuNote(
        event_id=event.event_id,
        pitch=event.pitch,
        token=degree_label(degree, accidental),
        degree=degree,
        accidental=accidental,
        octave=octave,
        duration_label=symbol,
        dots=dots,
        approximate=approximate,
        tie=tie_map.get(event.event_id),
        is_rest=False,
        chord_id=event.chord_id,
        chord_size=max(1, len(members)),
        chord_index=chord_index,
        is_chord_head=chord_index == 0,
        mapped_key=key_definition.key_id if key_definition else None,
        key_label=key_definition.label if key_definition else None,
        width=width,
        confidence=event.confidence,
        start_time=event.start_time,
        duration=event.duration,
        beat_in_measure=event.beat,
    )


def _ensure_chord_consistency(measure: JianpuMeasure) -> None:
    """Chords must keep their members adjacent and ordered by pitch."""
    ordered: List[JianpuNote] = []
    index = 0
    notes = measure.notes
    while index < len(notes):
        note = notes[index]
        if note.chord_id:
            group = [n for n in notes if n.chord_id == note.chord_id]
            group.sort(key=lambda n: n.pitch or 0)
            for position, member in enumerate(group):
                member.chord_index = position
                member.chord_size = len(group)
                member.is_chord_head = position == 0
            ordered.extend(group)
            index += len(group)
        else:
            ordered.append(note)
            index += 1
    measure.notes = ordered
