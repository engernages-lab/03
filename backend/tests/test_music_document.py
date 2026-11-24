"""MusicDocument engine tests: structure, invariants, serialisation, migration."""

from __future__ import annotations

import json

import pytest

from app.core.errors import ValidationAppError
from app.schemas.music_document import (
    MusicDocument,
    NoteEvent,
    SourceMetadata,
    TimeSignature,
    empty_document,
    new_id,
)
from app.services import music_document as core
from app.services.music_document.serialization import (
    DocumentVersionError,
    document_from_dict,
    document_from_json,
    document_to_dict,
    document_to_json,
    migrate,
)


# ---------------------------------------------------------------------------
# construction
# ---------------------------------------------------------------------------

def test_empty_document_is_valid_and_has_one_track():
    document = empty_document("练习曲", "测试艺人")
    assert document.title == "练习曲"
    assert len(document.tracks) == 1
    assert document.events == []
    assert document.duration == 0.0
    assert document.schema_version == 1
    assert document.keyboard_layout.key_count == 7


def test_document_requires_a_track():
    with pytest.raises(ValueError, match="at least one track"):
        MusicDocument(tracks=[], events=[])


def test_event_must_reference_existing_track():
    payload = empty_document().model_dump()
    payload["events"] = [
        {"event_id": "e1", "pitch": 60, "start_time": 0, "duration": 1, "track_id": "nope"}
    ]
    with pytest.raises(ValueError, match="unknown track"):
        MusicDocument.model_validate(payload)


def test_duplicate_event_ids_rejected():
    payload = empty_document().model_dump()
    payload["events"] = [
        {"event_id": "dup", "pitch": 60, "start_time": 0, "duration": 1, "track_id": "t1"},
        {"event_id": "dup", "pitch": 62, "start_time": 1, "duration": 1, "track_id": "t1"},
    ]
    with pytest.raises(ValueError, match="duplicate event_id"):
        MusicDocument.model_validate(payload)


# ---------------------------------------------------------------------------
# time / measure / beat
# ---------------------------------------------------------------------------

def test_single_note_position_and_duration():
    document = empty_document(tempo=120)
    event = core.add_event(document, pitch=60, start_time=0.0, duration=4.0)
    assert event.measure == 1
    assert event.beat == 1.0
    assert document.duration == pytest.approx(2.0)  # 4 beats @120bpm = 2s
    assert event.mapped_key == "k0"


def test_note_inside_second_measure_4_4():
    document = empty_document()
    event = core.add_event(document, pitch=64, start_time=4.0, duration=1.0)
    assert event.measure == 2
    assert event.beat == 1.0


def test_cross_measure_note_keeps_start_position():
    document = empty_document()
    event = core.add_event(document, pitch=62, start_time=3.5, duration=2.0)
    assert event.measure == 1
    assert event.beat == 4.5
    assert document.max_end_beat() == pytest.approx(5.5)
    assert document.total_measures() == 2


def test_three_four_time_signature():
    document = empty_document(time_signature=TimeSignature(numerator=3, denominator=4))
    assert document.beats_per_measure == pytest.approx(3.0)
    event = core.add_event(document, pitch=60, start_time=3.0, duration=1.0)
    assert event.measure == 2
    assert event.beat == 1.0


def test_six_eight_time_signature():
    document = empty_document(time_signature=TimeSignature(numerator=6, denominator=8))
    assert document.beats_per_measure == pytest.approx(3.0)
    event = core.add_event(document, pitch=60, start_time=6.0, duration=1.5)
    assert event.measure == 3
    assert event.beat == 1.0


def test_tempo_change_updates_duration_only():
    document = empty_document(tempo=60)
    core.add_event(document, pitch=60, start_time=0.0, duration=4.0)
    assert document.duration == pytest.approx(4.0)
    core.set_tempo(document, 120)
    assert document.duration == pytest.approx(2.0)


def test_time_signature_change_reindexes_measures():
    document = empty_document(time_signature=TimeSignature(numerator=4, denominator=4))
    event = core.add_event(document, pitch=60, start_time=4.0, duration=1.0)
    assert event.measure == 2
    core.set_time_signature(document, 3, 4)
    refreshed = document.event_by_id(event.event_id)
    assert refreshed is not None
    assert refreshed.measure == 2
    assert refreshed.beat == 2.0


# ---------------------------------------------------------------------------
# chords, rests, tracks, polyphony
# ---------------------------------------------------------------------------

def test_chord_notes_share_chord_id():
    document = empty_document()
    a = core.add_event(document, pitch=60, start_time=0.0, duration=2.0)
    b = core.add_event(document, pitch=64, start_time=0.0, duration=2.0)
    c = core.add_event(document, pitch=67, start_time=0.0, duration=2.0)
    assert a.chord_id == b.chord_id == c.chord_id
    assert a.chord_id is not None

    solo = core.add_event(document, pitch=72, start_time=2.0, duration=2.0)
    assert solo.chord_id is None


def test_rest_is_explicit_event_without_pitch():
    document = empty_document()
    rest = core.add_event(document, pitch=None, start_time=0.0, duration=1.0, kind="rest")
    assert rest.kind == "rest"
    assert rest.pitch is None
    assert rest.mapped_key is None
    assert document.duration == pytest.approx(0.5)


def test_multiple_tracks_and_durations():
    document = empty_document()
    second = core.add_track(document, "低音")
    core.add_event(document, pitch=60, start_time=0.0, duration=0.5)
    core.add_event(document, pitch=64, start_time=0.0, duration=1.0)
    core.add_event(document, pitch=48, start_time=0.0, duration=4.0, track_id=second.track_id)
    assert len(document.tracks) == 2
    durations = sorted(e.duration for e in document.events)
    assert durations == [0.5, 1.0, 4.0]
    summary = {row["track_id"]: row["events"] for row in core.track_summary(document)}
    assert summary[second.track_id] == 1


def test_octave_notes_map_to_distinct_keys_in_chromatic_layout():
    from app.schemas.keyboard import chroma_layout

    document = empty_document(keyboard_layout=chroma_layout())
    low = core.add_event(document, pitch=60, start_time=0.0, duration=1.0)
    high = core.add_event(document, pitch=72, start_time=1.0, duration=1.0)
    assert low.mapped_key == "k0"
    assert high.mapped_key is None  # C5 is outside the one-octave chromatic layout


def test_overlapping_same_pitch_is_reported():
    document = empty_document()
    core.add_event(document, pitch=60, start_time=0.0, duration=2.0)
    core.add_event(document, pitch=60, start_time=1.0, duration=2.0)
    overlaps = core.find_overlaps(document)
    assert len(overlaps) == 1
    assert overlaps[0]["pitch"] == 60
    assert overlaps[0]["overlap_beats"] == pytest.approx(1.0)
    codes = {finding["code"] for finding in core.validate_document(document)}
    assert "EVENT_OVERLAP" in codes


# ---------------------------------------------------------------------------
# editing primitives
# ---------------------------------------------------------------------------

def test_update_event_changes_only_requested_field():
    document = empty_document()
    event = core.add_event(document, pitch=60, start_time=1.0, duration=1.0)
    updated = core.update_event(document, event.event_id, {"velocity": 40})
    assert updated.velocity == 40
    assert updated.pitch == 60
    assert updated.start_time == 1.0


def test_update_event_rejects_navigation_fields():
    document = empty_document()
    event = core.add_event(document, pitch=60, start_time=0.0, duration=1.0)
    with pytest.raises(ValidationAppError):
        core.update_event(document, event.event_id, {"measure": 9})


def test_delete_event_removes_from_document():
    document = empty_document()
    event = core.add_event(document, pitch=60, start_time=0.0, duration=1.0)
    core.delete_event(document, event.event_id)
    assert document.events == []
    assert document.duration == 0.0


def test_transpose_clamps_at_midi_bounds():
    document = empty_document()
    core.add_event(document, pitch=125, start_time=0.0, duration=1.0)
    changed = core.transpose(document, 12)
    assert changed == 0
    assert document.events[0].pitch == 125


def test_quantize_snaps_to_grid():
    document = empty_document()
    event = core.add_event(document, pitch=60, start_time=0.37, duration=0.61)
    core.quantize_events(document, divisions=4)
    refreshed = document.event_by_id(event.event_id)
    assert refreshed is not None
    assert refreshed.start_time == pytest.approx(0.25)
    assert refreshed.duration == pytest.approx(0.5)


def test_add_event_rejects_invalid_time():
    document = empty_document()
    with pytest.raises(ValidationAppError):
        core.add_event(document, pitch=60, start_time=-1.0, duration=1.0)
    with pytest.raises(ValidationAppError):
        core.add_event(document, pitch=60, start_time=0.0, duration=0.0)


def test_add_event_rejects_unknown_track():
    document = empty_document()
    with pytest.raises(Exception):
        core.add_event(document, pitch=60, start_time=0.0, duration=1.0, track_id="ghost")


# ---------------------------------------------------------------------------
# serialisation / validation / versioning
# ---------------------------------------------------------------------------

def _sample_document() -> MusicDocument:
    document = empty_document("序列化测试", "PocketScore", tempo=100)
    core.add_event(document, pitch=60, start_time=0.0, duration=1.0)
    core.add_event(document, pitch=64, start_time=0.0, duration=1.0)
    core.add_event(document, pitch=None, start_time=1.0, duration=1.0, kind="rest")
    core.add_event(document, pitch=67, start_time=2.0, duration=2.0)
    return document


def test_serialisation_roundtrip_is_stable():
    document = _sample_document()
    first = document_to_json(document)
    second = document_to_json(document_from_json(first))
    assert first == second
    restored = document_from_dict(json.loads(first))
    assert len(restored.events) == 4
    assert restored.tracks[0].track_id == document.tracks[0].track_id


def test_dict_contains_every_required_field():
    data = document_to_dict(_sample_document())
    for field in (
        "document_id", "title", "artist", "tempo", "time_signature", "key_signature",
        "duration", "tracks", "events", "keyboard_layout", "notation_settings",
        "source_metadata", "created_at", "updated_at",
    ):
        assert field in data
    event = data["events"][0]
    for field in (
        "event_id", "pitch", "start_time", "duration", "velocity", "track_id",
        "measure", "beat", "mapped_key",
    ):
        assert field in event


def test_v0_migration_renames_time_and_length():
    v0 = {
        "document_id": "legacy-doc",
        "title": "旧版本",
        "events": [
            {"event_id": "e1", "pitch": 60, "time": 0.0, "length": 1.0, "track_id": "t1"},
            {"event_id": "e2", "pitch": 62, "time": 1.0, "length": 1.0, "track_id": "t1"},
        ],
        "tracks": [{"track_id": "t1", "name": "主旋律"}],
    }
    migrated = migrate(v0)
    assert migrated["schema_version"] == 1
    assert migrated["events"][0]["start_time"] == 0.0
    assert migrated["events"][0]["duration"] == 1.0
    assert migrated["events"][0]["kind"] == "note"

    document = document_from_dict(v0)
    assert document.document_id == "legacy-doc"
    assert len(document.events) == 2


def test_unsupported_version_is_reported():
    with pytest.raises(DocumentVersionError) as exc:
        migrate({"schema_version": 99, "events": []})
    assert exc.value.status_code == 422
    assert exc.value.code == "DOCUMENT_VERSION_UNSUPPORTED"


def test_invalid_payload_raises_validation_error():
    with pytest.raises(ValidationAppError):
        document_from_json("{not json}")
    with pytest.raises(ValidationAppError):
        document_from_dict({"title": "缺少轨道", "tracks": [], "events": []})


def test_invalid_pitch_rejected():
    with pytest.raises(ValueError):
        NoteEvent(event_id="x", pitch=200, start_time=0, duration=1, track_id="t1")


def test_unknown_key_signature_rejected():
    with pytest.raises(ValueError, match="unsupported key_signature"):
        MusicDocument(tracks=[], events=[], key_signature="H#")


def test_source_metadata_roundtrip():
    document = empty_document(source=SourceMetadata(kind="midi", filename="demo.mid"))
    restored = document_from_dict(document_to_dict(document))
    assert restored.source_metadata.kind == "midi"
    assert restored.source_metadata.filename == "demo.mid"


def test_new_id_is_twelve_hex_chars():
    identifier = new_id()
    assert len(identifier) == 12
    int(identifier, 16)  # raises if not hex
