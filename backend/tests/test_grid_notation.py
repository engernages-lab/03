"""Grid notation engine tests (owner: pocket-grid-notation)."""

from __future__ import annotations

import pytest

from app.core.errors import ValidationAppError
from app.schemas.keyboard import chroma_layout, default_layout
from app.schemas.music_document import TimeSignature, empty_document
from app.services import music_document as core
from app.services.notation.grid import REST_KEY_ID, compile_grid


def build_document(**kwargs):
    document = empty_document(**kwargs)
    return document


# ---------------------------------------------------------------------------
# layout of the grid
# ---------------------------------------------------------------------------

def test_four_four_has_sixteen_slots_per_measure():
    document = build_document()
    view = compile_grid(document, divisions=4)
    assert view.slots_per_measure == 16
    assert len(view.measures) == 1
    assert view.stats.slots == 16


def test_three_four_has_twelve_slots():
    document = build_document(time_signature=TimeSignature(numerator=3, denominator=4))
    view = compile_grid(document, divisions=4)
    assert view.slots_per_measure == 12


def test_six_eight_has_twelve_slots():
    document = build_document(time_signature=TimeSignature(numerator=6, denominator=8))
    view = compile_grid(document, divisions=4)
    assert view.slots_per_measure == 12


def test_rows_follow_layout_order_and_labels():
    document = build_document()
    view = compile_grid(document)
    assert [row.key_id for row in view.rows] == [f"k{i}" for i in range(7)]
    assert view.rows[0].label == "C4"
    assert view.rows[0].pitch == 60
    assert len(view.rows[0].cells) == view.stats.slots


def test_divisions_alternative_values():
    document = build_document()
    view = compile_grid(document, divisions=8)
    assert view.slots_per_measure == 32
    with pytest.raises(ValidationAppError):
        compile_grid(document, divisions=3)


# ---------------------------------------------------------------------------
# note placement / durations
# ---------------------------------------------------------------------------

def test_whole_beat_note_spans_four_cells():
    document = build_document()
    core.add_event(document, pitch=60, start_time=0.0, duration=1.0)
    view = compile_grid(document, divisions=4)
    row = view.rows[0]
    assert row.cells[0].state == "note"
    assert [cell.state for cell in row.cells[1:4]] == ["continuation"] * 3
    assert row.cells[4].state == "empty"
    assert row.cells[0].span == 4
    assert view.stats.notes == 1


def test_half_and_sixteenth_durations():
    document = build_document()
    core.add_event(document, pitch=62, start_time=0.0, duration=2.0)   # half note
    core.add_event(document, pitch=64, start_time=2.0, duration=0.25)  # sixteenth
    view = compile_grid(document, divisions=4)
    row1 = next(r for r in view.rows if r.key_id == "k1")
    row2 = next(r for r in view.rows if r.key_id == "k2")
    assert row1.cells[0].span == 8
    assert row2.cells[8].span == 1
    assert row2.cells[8].state == "note"
    assert row2.cells[9].state == "empty"


def test_chord_members_occupy_same_slot_in_different_rows():
    document = build_document()
    core.add_event(document, pitch=60, start_time=0.0, duration=1.0)
    core.add_event(document, pitch=64, start_time=0.0, duration=1.0)
    core.add_event(document, pitch=67, start_time=0.0, duration=1.0)
    view = compile_grid(document)
    active = [row for row in view.rows if row.cells[0].state == "note"]
    assert len(active) == 3
    chord_ids = {row.cells[0].chord_id for row in active}
    assert len(chord_ids) == 1
    assert view.stats.chords == 1


def test_rest_is_rendered_in_rest_lane():
    document = build_document()
    core.add_event(document, pitch=None, start_time=0.0, duration=1.0, kind="rest")
    view = compile_grid(document)
    assert view.rest_row is not None
    assert view.rest_row.key_id == REST_KEY_ID
    assert view.rest_row.cells[0].state == "rest"
    assert view.rest_row.cells[1].state == "continuation"
    assert view.stats.rests == 1


def test_no_rest_row_when_no_rests():
    document = build_document()
    core.add_event(document, pitch=60, start_time=0.0, duration=1.0)
    view = compile_grid(document)
    assert view.rest_row is None


def test_cross_measure_note_continues_into_next_measure():
    document = build_document()
    core.add_event(document, pitch=65, start_time=3.5, duration=2.0)
    view = compile_grid(document, divisions=4)
    row = next(r for r in view.rows if r.key_id == "k3")
    # starts on slot 14 (beat 3.5 of measure 1)
    assert row.cells[14].state == "note"
    assert row.cells[15].state == "continuation"
    # continues into measure 2 slots 0..5 (2 beats = 8 slots total)
    assert row.cells[16].state == "continuation"
    assert row.cells[21].state == "continuation"
    assert row.cells[22].state == "empty"
    assert len(view.measures) == 2


def test_note_at_second_measure_start():
    document = build_document()
    core.add_event(document, pitch=60, start_time=4.0, duration=1.0)
    view = compile_grid(document, divisions=4)
    assert view.rows[0].cells[16].state == "note"
    assert view.rows[0].cells[16].measure == 2
    assert view.rows[0].cells[16].slot == 0


def test_unmapped_note_is_reported_not_dropped():
    document = build_document()
    core.add_event(document, pitch=61, start_time=0.0, duration=1.0)  # C#4 not on 7-key layout
    view = compile_grid(document)
    assert len(view.unmapped) == 1
    assert view.unmapped[0].pitch == 61
    assert view.unmapped[0].pitch_name == "C#4"
    assert view.stats.unmapped == 1
    assert all(cell.state == "empty" for row in view.rows for cell in row.cells)


def test_layout_change_updates_rows_but_not_notes():
    document = build_document()
    core.add_event(document, pitch=61, start_time=0.0, duration=1.0)
    before = compile_grid(document)
    assert before.stats.unmapped == 1

    after = compile_grid(document, chroma_layout())
    assert len(after.rows) == 12
    assert after.stats.unmapped == 0
    assert after.rows[1].cells[0].state == "note"  # C#4 = k1


def test_compilation_is_deterministic():
    document = build_document()
    core.add_event(document, pitch=60, start_time=0.0, duration=1.0)
    core.add_event(document, pitch=64, start_time=1.0, duration=0.5)
    first = compile_grid(document).model_dump()
    second = compile_grid(document).model_dump()
    assert first == second


def test_empty_document_still_has_one_measure():
    document = build_document()
    view = compile_grid(document)
    assert len(view.measures) == 1
    assert view.stats.notes == 0
    assert all(cell.state == "empty" for row in view.rows for cell in row.cells)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def _seed_document(client) -> str:
    created = client.post("/api/v1/documents", json={"title": "格子谱测试"}).json()
    document_id = created["document_id"]
    client.post(
        f"/api/v1/documents/{document_id}/edits",
        json={
            "operations": [
                {"op": "add_note", "pitch": 60, "start_time": 0.0, "duration": 1.0},
                {"op": "add_note", "pitch": 64, "start_time": 0.0, "duration": 1.0},
                {"op": "add_rest", "start_time": 1.0, "duration": 1.0},
            ]
        },
    )
    return document_id


def test_api_grid_returns_view_model(client):
    document_id = _seed_document(client)
    response = client.get(f"/api/v1/notation/{document_id}/grid")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["document_id"] == document_id
    assert body["slots_per_measure"] == 16
    assert body["stats"]["notes"] == 2
    assert body["stats"]["rests"] == 1
    assert len(body["rows"]) == 7
    assert body["rest_row"]["cells"][4]["state"] == "rest"


def test_api_grid_rejects_bad_divisions(client):
    document_id = _seed_document(client)
    response = client.get(f"/api/v1/notation/{document_id}/grid", params={"divisions": 5})
    assert response.status_code == 422


def test_api_grid_svg_export(client):
    document_id = _seed_document(client)
    response = client.get(f"/api/v1/notation/{document_id}/grid.svg")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    body = response.text
    assert body.startswith("<svg")
    assert "格子谱测试" in body
    assert body.rstrip().endswith("</svg>")
