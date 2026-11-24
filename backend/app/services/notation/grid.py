"""Grid notation engine: MusicDocument + KeyboardLayout -> GridViewModel.

Owner: pocket-grid-notation skill.  A pure function: no I/O, no clock, no
randomness.  Pitch -> key resolution is delegated to the keyboard engine so the
mapping algorithm exists in exactly one place.
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from app.core.errors import ValidationAppError
from app.schemas.keyboard import KeyboardLayout
from app.schemas.music_document import EPSILON, MusicDocument, NoteEvent
from app.services.keyboard.mapping import KeyboardMappingEngine, pitch_name
from app.services.music_document.timing import beats_per_measure, duration_in_slots, measure_start

MAX_CELLS = 40_000
REST_KEY_ID = "*rest*"

CellState = Literal["empty", "note", "rest", "continuation"]


class GridCell(BaseModel):
    measure: int
    slot: int
    state: CellState = "empty"
    start_time: float = 0.0
    duration: float = 0.0
    event_id: Optional[str] = None
    chord_id: Optional[str] = None
    span: int = 1
    velocity: int = 0
    pitch: Optional[int] = None
    label: Optional[str] = None
    color: Optional[str] = None


class GridRow(BaseModel):
    key_id: str
    label: str
    index: int
    color: str
    pitch: Optional[int] = None
    pitch_name: Optional[str] = None
    cells: List[GridCell] = Field(default_factory=list)


class GridMeasure(BaseModel):
    measure: int
    start_beat: float
    beats: float
    slots: int
    start_slot: int


class UnmappedNote(BaseModel):
    event_id: str
    pitch: int
    pitch_name: str
    start_time: float
    duration: float
    measure: int
    reason: str = "outside_layout"


class GridStats(BaseModel):
    notes: int = 0
    rests: int = 0
    chords: int = 0
    measures: int = 0
    slots: int = 0
    unmapped: int = 0


class GridViewModel(BaseModel):
    document_id: str
    title: str
    artist: str
    layout_id: str
    layout_name: str
    tempo: float
    time_signature: str
    key_signature: str
    divisions: int
    slots_per_measure: int
    measures: List[GridMeasure] = Field(default_factory=list)
    rows: List[GridRow] = Field(default_factory=list)
    rest_row: Optional[GridRow] = None
    unmapped: List[UnmappedNote] = Field(default_factory=list)
    stats: GridStats = Field(default_factory=GridStats)


def compile_grid(
    document: MusicDocument,
    layout: Optional[KeyboardLayout] = None,
    divisions: int = 4,
) -> GridViewModel:
    if divisions not in (1, 2, 4, 8, 16):
        raise ValidationAppError(
            "divisions must be one of 1, 2, 4, 8, 16", code="INVALID_DIVISIONS"
        )
    layout = layout or document.keyboard_layout
    engine = KeyboardMappingEngine(layout)

    measure_beats = beats_per_measure(document.time_signature)
    slots_per_measure = max(1, int(round(measure_beats * divisions)))
    total_measures = max(1, document.total_measures())
    total_slots = total_measures * slots_per_measure
    row_count = max(1, len(layout.keys))
    if total_slots * (row_count + 1) > MAX_CELLS:
        raise ValidationAppError(
            f"grid would contain more than {MAX_CELLS} cells; reduce divisions or measures",
            code="NOTATION_TOO_LARGE",
            status_code=413,
            details={"slots": total_slots, "rows": row_count + 1},
        )

    measures: List[GridMeasure] = []
    for index in range(total_measures):
        number = index + 1
        measures.append(
            GridMeasure(
                measure=number,
                start_beat=measure_start(number, document.time_signature),
                beats=measure_beats,
                slots=slots_per_measure,
                start_slot=index * slots_per_measure,
            )
        )

    def empty_row(key_id: str, label: str, index: int, color: str, pitch: Optional[int]) -> GridRow:
        cells = [
            GridCell(measure=slot // slots_per_measure + 1, slot=slot % slots_per_measure)
            for slot in range(total_slots)
        ]
        return GridRow(
            key_id=key_id,
            label=label,
            index=index,
            color=color,
            pitch=pitch,
            pitch_name=pitch_name(pitch) if pitch is not None else None,
            cells=cells,
        )

    rows = [
        empty_row(key.key_id, key.label, key.index, key.color, engine.absolute_pitch(key))
        for key in layout.sorted_keys()
    ]
    row_by_key_id = {row.key_id: row for row in rows}
    rest_row = empty_row(REST_KEY_ID, "休止", -1, "#5b6d8c", None)

    stats = GridStats(measures=total_measures, slots=total_slots)
    unmapped: List[UnmappedNote] = []
    chord_ids = set()

    for event in document.events:
        slot_start = int(round(event.start_time * divisions))
        if slot_start >= total_slots:
            slot_start = total_slots - 1
        span = duration_in_slots(event.duration, divisions)
        span = max(1, min(span, total_slots - slot_start))

        target: Optional[GridRow]
        state: CellState
        if event.kind == "rest":
            target = rest_row
            state = "rest"
            stats.rests += 1
        else:
            mapping = engine.resolve(event.pitch) if event.pitch is not None else None
            target = row_by_key_id.get(mapping.key_id) if mapping and mapping.key_id else None
            state = "note"
            if target is None:
                unmapped.append(
                    UnmappedNote(
                        event_id=event.event_id,
                        pitch=event.pitch or 0,
                        pitch_name=pitch_name(event.pitch or 0),
                        start_time=event.start_time,
                        duration=event.duration,
                        measure=event.measure,
                    )
                )
                stats.unmapped += 1
                continue
            stats.notes += 1
            if event.chord_id:
                chord_ids.add(event.chord_id)

        if event.chord_id:
            chord_ids.add(event.chord_id)

        for offset in range(span):
            slot = slot_start + offset
            cell = target.cells[slot]
            cell.state = state if offset == 0 else "continuation"
            cell.start_time = event.start_time
            cell.duration = event.duration
            cell.event_id = event.event_id
            cell.chord_id = event.chord_id
            cell.span = span
            cell.velocity = event.velocity
            cell.pitch = event.pitch
            cell.label = target.label
            cell.color = target.color

    stats.chords = len(chord_ids)
    if stats.rests == 0:
        rest_row = None

    return GridViewModel(
        document_id=document.document_id,
        title=document.title,
        artist=document.artist,
        layout_id=layout.layout_id,
        layout_name=layout.name,
        tempo=document.tempo,
        time_signature=document.time_signature.as_label(),
        key_signature=document.key_signature,
        divisions=divisions,
        slots_per_measure=slots_per_measure,
        measures=measures,
        rows=rows,
        rest_row=rest_row,
        unmapped=unmapped,
        stats=stats,
    )
