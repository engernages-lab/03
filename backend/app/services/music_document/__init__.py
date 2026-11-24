"""MusicDocument engine: invariants, editing primitives, serialisation."""

from app.services.music_document.engine import (
    add_event,
    add_track,
    delete_event,
    delete_track,
    detect_chords,
    find_overlaps,
    move_event_to_key,
    quantize_events,
    reindex,
    require_event,
    require_track,
    set_tempo,
    set_time_signature,
    sort_events,
    track_summary,
    transpose,
    update_event,
    validate_document,
)
from app.services.music_document.serialization import (
    document_from_dict,
    document_from_json,
    document_to_dict,
    document_to_json,
    migrate,
    safe_document_from_json,
)
from app.services.music_document.timing import (
    beats_per_measure,
    beats_to_seconds,
    locate_beat,
    measure_start,
    quantize,
    seconds_to_beats,
)

__all__ = [
    "add_event", "add_track", "delete_event", "delete_track", "detect_chords",
    "find_overlaps", "move_event_to_key", "quantize_events", "reindex",
    "require_event", "require_track", "set_tempo", "set_time_signature",
    "sort_events", "track_summary", "transpose", "update_event", "validate_document",
    "document_from_dict", "document_from_json", "document_to_dict", "document_to_json",
    "migrate", "safe_document_from_json",
    "beats_per_measure", "beats_to_seconds", "locate_beat", "measure_start",
    "quantize", "seconds_to_beats",
]
