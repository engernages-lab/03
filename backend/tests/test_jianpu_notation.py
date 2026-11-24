"""Jianpu (numbered notation) engine tests (owner: pocket-jianpu-notation)."""

from __future__ import annotations

import pytest

from app.schemas.keyboard import chroma_layout
from app.schemas.music_document import empty_document
from app.services import music_document as core
from app.services.notation.jianpu import compile_jianpu, duration_symbol
from app.services.notation.keys import degree_for_pitch, parse_key_signature


def note_views(document, layout=None, key_signature=None):
    view = compile_jianpu(document, layout, key_signature)
    return view, [note for measure in view.measures for note in measure.notes]


# ---------------------------------------------------------------------------
# key parsing
# ---------------------------------------------------------------------------

def test_parse_major_and_minor_keys():
    assert parse_key_signature("C").mode == "major"
    assert parse_key_signature("F#").tonic_pc == 6
    assert parse_key_signature("Am").mode == "minor"
    assert parse_key_signature("Am").tonic_pc == 9
    assert parse_key_signature("Bbm").mode == "minor"
    assert parse_key_signature("Bb").mode == "major"


def test_invalid_key_signature_rejected():
    with pytest.raises(Exception) as exc:
        parse_key_signature("H")
    assert getattr(exc.value, "code", None) == "UNSUPPORTED_KEY_SIGNATURE"


# ---------------------------------------------------------------------------
# pitch -> degree
# ---------------------------------------------------------------------------

def test_c_major_degrees_and_octaves():
    key = parse_key_signature("C")
    assert degree_for_pitch(60, key) == (1, None, 0)   # C4
    assert degree_for_pitch(62, key) == (2, None, 0)   # D4
    assert degree_for_pitch(64, key) == (3, None, 0)   # E4
    assert degree_for_pitch(65, key) == (4, None, 0)
    assert degree_for_pitch(67, key) == (5, None, 0)
    assert degree_for_pitch(69, key) == (6, None, 0)
    assert degree_for_pitch(71, key) == (7, None, 0)
    assert degree_for_pitch(72, key) == (1, None, 1)   # C5, dot above
    assert degree_for_pitch(48, key) == (1, None, -1)  # C3, dot below


def test_chromatic_notes_get_single_accidental():
    key = parse_key_signature("C")
    assert degree_for_pitch(61, key) == (1, "#", 0)   # C#4 -> #1
    assert degree_for_pitch(66, key) == (4, "#", 0)   # F#4 -> #4
    # Bb4 is one semitone from both A and B; sharp spelling is the default.
    assert degree_for_pitch(70, key) == (6, "#", 0)
    assert degree_for_pitch(70, key, prefer_flat=True) == (7, "b", 0)


def test_a_minor_tonic_is_degree_one():
    key = parse_key_signature("Am")
    assert degree_for_pitch(69, key) == (1, None, 0)
    # C4 sits below the tonic octave (A4..G5), so it carries a dot below.
    assert degree_for_pitch(60, key) == (3, None, -1)
    assert degree_for_pitch(72, key) == (3, None, 0)  # C5 is in the tonic octave


def test_g_major_tonic_and_lower_fourth():
    key = parse_key_signature("G")
    assert degree_for_pitch(67, key) == (1, None, 0)   # G4
    assert degree_for_pitch(60, key) == (4, None, -1)  # C4 below the tonic octave


# ---------------------------------------------------------------------------
# durations
# ---------------------------------------------------------------------------

def test_duration_symbols():
    assert duration_symbol(4.0) == ("—", 0, False)
    assert duration_symbol(2.0) == ("-", 0, False)
    assert duration_symbol(1.0) == ("", 0, False)
    assert duration_symbol(0.5) == ("_", 0, False)
    assert duration_symbol(0.25) == ("=", 0, False)
    assert duration_symbol(1.5) == ("", 1, False)   # dotted quarter
    assert duration_symbol(3.0) == ("-", 1, False)  # dotted half


def test_odd_duration_is_flagged_approximate():
    symbol, dots, approximate = duration_symbol(0.37)
    assert approximate is True
    assert dots == 0


# ---------------------------------------------------------------------------
# compilation
# ---------------------------------------------------------------------------

def test_view_model_header_and_measures():
    document = empty_document("简谱测试", "QA", tempo=96)
    core.add_event(document, pitch=60, start_time=0.0, duration=1.0)
    view, notes = note_views(document)
    assert view.title == "简谱测试"
    assert view.tempo == 96
    assert view.time_signature == "4/4"
    assert view.tonic == "C"
    assert view.mode == "major"
    assert len(view.measures) == 1
    assert notes[0].token == "1"
    assert notes[0].duration_label == ""


def test_rest_renders_as_zero():
    document = empty_document()
    core.add_event(document, pitch=None, start_time=0.0, duration=1.0, kind="rest")
    view, notes = note_views(document)
    assert notes[0].is_rest is True
    assert notes[0].token == "0"
    assert view.stats.rests == 1


def test_chord_members_are_stacked_and_ordered():
    document = empty_document()
    core.add_event(document, pitch=60, start_time=0.0, duration=1.0)
    core.add_event(document, pitch=64, start_time=0.0, duration=1.0)
    core.add_event(document, pitch=67, start_time=0.0, duration=1.0)
    view, notes = note_views(document)
    assert view.stats.chords == 1
    chord_notes = [n for n in notes if n.chord_size == 3]
    assert len(chord_notes) == 3
    assert [n.chord_index for n in chord_notes] == [0, 1, 2]
    assert chord_notes[0].is_chord_head is True
    assert [n.token for n in chord_notes] == ["1", "3", "5"]


def test_ties_detected_for_adjacent_same_pitch():
    document = empty_document()
    first = core.add_event(document, pitch=60, start_time=0.0, duration=1.0)
    second = core.add_event(document, pitch=60, start_time=1.0, duration=1.0)
    view, notes = note_views(document)
    by_id = {n.event_id: n for n in notes}
    assert by_id[first.event_id].tie == "start"
    assert by_id[second.event_id].tie == "stop"
    assert view.stats.ties == 2


def test_no_tie_when_notes_are_not_adjacent():
    document = empty_document()
    first = core.add_event(document, pitch=60, start_time=0.0, duration=1.0)
    second = core.add_event(document, pitch=60, start_time=2.0, duration=1.0)
    _view, notes = note_views(document)
    by_id = {n.event_id: n for n in notes}
    assert by_id[first.event_id].tie is None
    assert by_id[second.event_id].tie is None


def test_key_labels_come_from_layout():
    document = empty_document()
    core.add_event(document, pitch=64, start_time=0.0, duration=1.0)
    _view, notes = note_views(document)
    assert notes[0].mapped_key == "k2"
    assert notes[0].key_label == "E4"


def test_unmapped_pitch_still_renders_number():
    document = empty_document()
    core.add_event(document, pitch=61, start_time=0.0, duration=1.0)
    view, notes = note_views(document)
    assert notes[0].token == "#1"
    assert notes[0].mapped_key is None
    assert view.stats.unmapped == 1


def test_chromatic_layout_labels_change_with_layout():
    document = empty_document(keyboard_layout=chroma_layout())
    core.add_event(document, pitch=61, start_time=0.0, duration=1.0)
    _view, notes = note_views(document)
    assert notes[0].key_label == "C#4"
    assert notes[0].token == "#1"


def test_measures_and_system_layout():
    document = empty_document()
    for index in range(8):
        core.add_event(document, pitch=60 + (index % 7) * 2, start_time=index * 4.0, duration=1.0)
    view, _notes = note_views(document)
    assert len(view.measures) >= 8
    assert view.max_notes_per_line == 16
    assert view.measures[0].system_index == 0


def test_deterministic_output():
    document = empty_document()
    core.add_event(document, pitch=60, start_time=0.0, duration=1.0)
    core.add_event(document, pitch=62, start_time=1.0, duration=0.5)
    first = compile_jianpu(document).model_dump()
    second = compile_jianpu(document).model_dump()
    assert first == second


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def _seed(client) -> str:
    document_id = client.post("/api/v1/documents", json={"title": "简谱 API"}).json()["document_id"]
    client.post(
        f"/api/v1/documents/{document_id}/edits",
        json={
            "operations": [
                {"op": "add_note", "pitch": 60, "start_time": 0.0, "duration": 1.0},
                {"op": "add_note", "pitch": 62, "start_time": 1.0, "duration": 0.5},
                {"op": "add_rest", "start_time": 2.0, "duration": 1.0},
            ]
        },
    )
    return document_id


def test_api_jianpu_view(client):
    document_id = _seed(client)
    response = client.get(f"/api/v1/notation/{document_id}/jianpu")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["key_signature"] == "C"
    assert body["stats"]["notes"] == 2
    assert body["stats"]["rests"] == 1
    notes = [n for m in body["measures"] for n in m["notes"]]
    assert [n["token"] for n in notes] == ["1", "2", "0"]


def test_api_jianpu_text_export(client):
    document_id = _seed(client)
    response = client.get(f"/api/v1/notation/{document_id}/jianpu.txt")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    body = response.content.decode("utf-8")
    assert "1=C" in body
    assert "| 1 2/ 0 " in body
    assert "统计：" in body


def test_api_both_returns_dual_view_and_document(client):
    document_id = _seed(client)
    response = client.get(f"/api/v1/notation/{document_id}/both")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["document"]["document_id"] == document_id
    assert body["grid"]["stats"]["notes"] == 2
    assert body["jianpu"]["stats"]["notes"] == 2
    assert isinstance(body["findings"], list)


def test_api_jianpu_rejects_invalid_key(client):
    document_id = _seed(client)
    response = client.get(f"/api/v1/notation/{document_id}/jianpu", params={"key_signature": "H"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "UNSUPPORTED_KEY_SIGNATURE"
